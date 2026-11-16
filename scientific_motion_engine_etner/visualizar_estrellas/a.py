import logging
import warnings
from pathlib import Path

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.utils.exceptions import AstropyWarning
from astropy.visualization import AsinhStretch, ImageNormalize, ZScaleInterval
from astropy.wcs import WCS
from astroquery.simbad import Simbad
from photutils.detection import DAOStarFinder

warnings.filterwarnings("ignore", category=AstropyWarning)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ===================== CONFIGURACIÓN =====================
RUTA_FITS = (
    Path(__file__).resolve().parent.parent
    / "spherex_6_bandas"
    / "level2_2025W19_2B_0103_4D1_spx_l2b-v20-2025-247.fits"
)
UMBRAL_SIGMA = 5.0       # Sensibilidad de detección (mayor = menos estrellas)
TAMANO_ESTRELLA = 2.5    # FWHM: grosor estimado de la estrella en píxeles
RADIO_BUSQUEDA = 10.0    # Segundos de arco para buscar coincidencias en SIMBAD
INDICE_EJEMPLO = 0       # Qué estrella usar para explicar la matemática paso a paso
MOSTRAR_MAPA = True      # Mostrar la imagen con las estrellas marcadas

Simbad.TIMEOUT = 15      # Timeout de conexión en segundos
# =========================================================


# ─────────────────── CARGA ───────────────────
def cargar_datos_fits(ruta):
    """Carga las 4 extensiones estándar de un FITS SPHEREx L2b y el WCS."""
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró: {ruta}")

    log.info("Cargando archivo: %s...", ruta.name)
    with fits.open(ruta) as hdul:
        return {
            "img": hdul["IMAGE"].data.astype(float).copy(),
            "var": hdul["VARIANCE"].data.astype(float).copy(),
            "flags": hdul["FLAGS"].data.copy(),
            "zodi": hdul["ZODI"].data.astype(float).copy(),
            "wcs": WCS(hdul["IMAGE"].header),
        }


# ─────────────────── PREPROCESAMIENTO ───────────────────
def preprocesar(datos):
    """Resta zodíaco, enmascara píxeles dañados (NaN) y calcula SNR."""
    img, var, flags, zodi = datos["img"], datos["var"], datos["flags"], datos["zodi"]

    # 1. Restar fondo zodiacal y anular píxeles con FLAGS > 0
    señal = np.where(flags == 0, img - zodi, np.nan)

    # 2. Mapa SNR protegido contra varianza ≤ 0
    with np.errstate(divide="ignore", invalid="ignore"):
        snr = np.where(var > 0, señal / np.sqrt(var), np.nan)

    # 3. Nivel de ruido base (para normalización visual)
    ruido_sigma = np.nanmedian(np.sqrt(np.where(var > 0, var, np.nan)))

    return señal, snr, ruido_sigma


# ─────────────────── DETECCIÓN ───────────────────
def detectar_estrellas(señal, snr, wcs):
    """Detecta estrellas sobre el mapa SNR limpio y devuelve píxeles + coordenadas."""
    mascara = np.isnan(snr)
    _, fondo_mediana, ruido = sigma_clipped_stats(snr, sigma=3.0, mask=mascara)

    buscador = DAOStarFinder(fwhm=TAMANO_ESTRELLA, threshold=UMBRAL_SIGMA * ruido)
    tabla = buscador(np.nan_to_num(snr - fondo_mediana), mask=mascara)

    if tabla is None or len(tabla) == 0:
        raise SystemExit("No se detectaron estrellas. Intenta bajar UMBRAL_SIGMA.")

    # Compatibilidad con distintas versiones de photutils
    col_x = "xcentroid" if "xcentroid" in tabla.colnames else "x_centroid"
    col_y = "ycentroid" if "ycentroid" in tabla.colnames else "y_centroid"
    x, y = np.asarray(tabla[col_x]), np.asarray(tabla[col_y])

    coordenadas = wcs.pixel_to_world(x, y)
    log.info("Se detectaron %d objetos brillantes.", len(tabla))
    return x, y, coordenadas


# ─────────────────── IDENTIFICACIÓN SIMBAD ───────────────────
def identificar_en_simbad(coordenadas, wcs):
    """Cross-match masivo: una sola query SIMBAD para todo el campo de visión."""
    n = len(coordenadas)

    try:
        # Centro y radio del campo completo
        ny, nx = wcs.pixel_shape if wcs.pixel_shape else (1, 1)
        centro = wcs.pixel_to_world(nx / 2, ny / 2)
        escalas = wcs.proj_plane_pixel_scales()  # grados/píxel (Quantity)
        escala = max(s.to_value(u.deg) if hasattr(s, 'to_value') else float(s) for s in escalas)
        radio_campo = max(nx, ny) * escala * u.deg

        log.info("Consultando SIMBAD (radio=%.2f arcmin)...", radio_campo.to(u.arcmin).value)
        catalogo = Simbad.query_region(centro, radius=radio_campo)
    except Exception as e:
        log.warning("SIMBAD no disponible: %s", e)
        return ["Sin conexión"] * n

    if catalogo is None or len(catalogo) == 0:
        log.info("SIMBAD no devolvió resultados para este campo.")
        return ["Desconocido"] * n

    # Compatibilidad entre versiones de astroquery
    col_ra = "ra" if "ra" in catalogo.colnames else "RA"
    col_dec = "dec" if "dec" in catalogo.colnames else "DEC"
    col_id = "main_id" if "main_id" in catalogo.colnames else "MAIN_ID"
    unidad = (u.deg, u.deg) if col_ra == "ra" else (u.hourangle, u.deg)

    cat_coords = SkyCoord(catalogo[col_ra], catalogo[col_dec], unit=unidad)

    # Cross-match: buscar la entrada más cercana del catálogo para cada estrella
    idx, sep, _ = coordenadas.match_to_catalog_sky(cat_coords)

    nombres = []
    for i, s in zip(idx, sep):
        if s < RADIO_BUSQUEDA * u.arcsec:
            nombres.append(str(catalogo[col_id][i]))
        else:
            nombres.append("Desconocido")

    identificados = sum(1 for n in nombres if n not in ("Desconocido", "Sin conexión"))
    log.info("Identificadas %d/%d estrellas en SIMBAD.", identificados, len(nombres))
    return nombres


# ─────────────────── VISUALIZACIÓN ───────────────────
def visualizar_campo(señal, ruido_sigma, wcs, x=None, y=None, nombres=None):
    """Muestra el campo en dos estilos con las estrellas detectadas marcadas."""
    vmin = 1.8 * ruido_sigma
    vmax = np.nanpercentile(señal, 99.95)

    norm = ImageNormalize(
        señal, vmin=vmin, vmax=vmax,
        stretch=AsinhStretch(a=0.05), clip=True,
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), facecolor="black")

    # Estilo 1: Cielo nocturno (B/N)
    ax1.imshow(señal, cmap="gray", origin="lower", norm=norm, interpolation="bicubic")
    ax1.set_title("Vista Telescopio Óptico (Cielo Negro)", color="white", pad=10)
    ax1.axis("off")

    # Estilo 2: Infrarrojo (SPHEREx)
    ax2.imshow(señal, cmap="afmhot", origin="lower", norm=norm, interpolation="bicubic")
    ax2.set_title("Vista Infrarroja (SPHEREx)", color="white", pad=10)
    ax2.axis("off")

    # Superponer estrellas detectadas
    if x is not None and y is not None:
        for ax in (ax1, ax2):
            ax.scatter(x, y, s=80, facecolors="none", edgecolors="cyan", linewidths=0.8)

        # Etiquetas con nombres (solo en panel infrarrojo)
        if nombres is not None:
            for xi, yi, nombre in zip(x, y, nombres):
                if nombre not in ("Desconocido", "Sin conexión"):
                    ax2.annotate(
                        nombre, (xi, yi),
                        xytext=(6, 6), textcoords="offset points",
                        color="cyan", fontsize=7,
                        arrowprops=dict(arrowstyle="-", color="cyan", lw=0.5),
                    )

    plt.tight_layout()
    plt.savefig("resultado_spherex.png", dpi=200, bbox_inches="tight", facecolor="black")
    log.info("Imagen guardada: resultado_spherex.png")
    plt.show()


def visualizar_snr(datos_img, snr):
    """Muestra la imagen original (ZScale) junto al mapa SNR limpio."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    vmin, vmax = ZScaleInterval().get_limits(datos_img)
    im1 = ax1.imshow(datos_img, cmap="viridis", origin="lower", vmin=vmin, vmax=vmax)
    ax1.set_title("IMAGE (ZScale)")
    plt.colorbar(im1, ax=ax1)

    im2 = ax2.imshow(snr, cmap="inferno", origin="lower", vmin=-2, vmax=8)
    ax2.set_title("Señal/Ruido Limpia (SNR en σ)")
    plt.colorbar(im2, ax=ax2)

    plt.tight_layout()
    plt.show()


# ─────────────────── EXPLICACIÓN WCS ───────────────────
def explicar_conversion_wcs(wcs, x, y):
    """Muestra paso a paso cómo se transforma un píxel (x, y) a coordenadas RA/Dec."""
    if wcs.sip is not None:
        log.warning("⚠️  Este FITS tiene correcciones SIP. El cálculo manual es aproximado.")

    matriz = wcs.pixel_scale_matrix
    pix_ref = wcs.wcs.crpix
    val_ref = wcs.wcs.crval

    # Paso 1: Distancia al píxel de referencia (+1 porque FITS cuenta desde 1 y Python desde 0)
    dx, dy = (x + 1) - pix_ref[0], (y + 1) - pix_ref[1]

    # Paso 2: Proyección al plano tangente (en radianes)
    xi = np.radians(matriz[0, 0] * dx + matriz[0, 1] * dy)
    eta = np.radians(matriz[1, 0] * dx + matriz[1, 1] * dy)

    # Paso 3: Trigonometría esférica hacia el cielo (Proyección TAN)
    ra_ref, dec_ref = np.radians(val_ref)
    ra_rad = ra_ref + np.arctan2(xi, np.cos(dec_ref) - eta * np.sin(dec_ref))
    dec_rad = np.arctan2(
        np.sin(dec_ref) + eta * np.cos(dec_ref),
        np.hypot(np.cos(dec_ref) - eta * np.sin(dec_ref), xi),
    )

    ra_manual, dec_manual = np.degrees(ra_rad) % 360, np.degrees(dec_rad)
    ra_astropy, dec_astropy = wcs.wcs_pix2world(x, y, 0)

    print(f"\n--- CÁLCULO PASO A PASO (Estrella en x={x:.1f}, y={y:.1f}) ---")
    print(f"1. Píxel de referencia (CRPIX) : ({pix_ref[0]:.1f}, {pix_ref[1]:.1f})")
    print(f"2. Coordenada base (CRVAL)     : RA={val_ref[0]:.4f}°, Dec={val_ref[1]:.4f}°")
    print(f"3. Desplazamiento (dx, dy)     : ({dx:.2f}, {dy:.2f}) píxeles")
    print(f"4. Resultado manual            : RA={ra_manual:.6f}°, Dec={dec_manual:.6f}°")
    print(f"5. Resultado Astropy           : RA={float(ra_astropy):.6f}°, Dec={float(dec_astropy):.6f}°\n")


# ─────────────────── PIPELINE PRINCIPAL ───────────────────
def main():
    # 1. Cargar
    datos = cargar_datos_fits(RUTA_FITS)
    wcs = datos["wcs"]

    # 2. Preprocesar (resta zodiacal + enmascarado consistente)
    señal, snr, ruido_sigma = preprocesar(datos)

    # 3. Detectar estrellas sobre el mapa SNR
    x, y, coordenadas = detectar_estrellas(señal, snr, wcs)

    # 4. Identificar con SIMBAD (1 sola query para todo el campo)
    nombres = identificar_en_simbad(coordenadas, wcs)

    # 5. Visualizar con estrellas superpuestas
    if MOSTRAR_MAPA:
        visualizar_campo(señal, ruido_sigma, wcs, x, y, nombres)
        visualizar_snr(datos["img"], snr)

    # 6. Explicar WCS para la primera estrella
    explicar_conversion_wcs(wcs, x[INDICE_EJEMPLO], y[INDICE_EJEMPLO])

    # 7. Resumen en consola
    print("\n╔══════════════════════════════════════════════╗")
    print("║         ESTRELLAS DETECTADAS                 ║")
    print("╠══════════════════════════════════════════════╣")
    for i, (xi, yi, coord, nombre) in enumerate(zip(x, y, coordenadas, nombres)):
        ra_str = f"{coord.ra.deg:.4f}°"
        dec_str = f"{coord.dec.deg:+.4f}°"
        print(f"║ #{i+1:>2}  pix=({xi:.0f},{yi:.0f})  RA={ra_str}  Dec={dec_str}  {nombre}")
    print("╚══════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()