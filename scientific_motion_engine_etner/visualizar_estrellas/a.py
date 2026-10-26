from pathlib import Path
import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.wcs import WCS
from astroquery.simbad import Simbad
from photutils.detection import DAOStarFinder

# ===================== CONFIGURACIÓN =====================
RUTA_FITS = (
    Path(__file__).resolve().parent.parent
    / "spherex_6_bandas"
    / "level2_2025W19_2B_0103_4D1_spx_l2b-v20-2025-247.fits"
)
EXTENSION = "IMAGE"      # Nombre o número de la extensión FITS
UMBRAL_SIGMA = 5.0       # Sensibilidad de detección (mayor = menos estrellas)
TAMANO_ESTRELLA = 2.5    # FWHM: grosor estimado de la estrella en píxeles
RADIO_BUSQUEDA = 10.0    # Segundos de arco para buscar coincidencias en SIMBAD
INDICE_EJEMPLO = 0       # Qué estrella usar para explicar la matemática paso a paso
MOSTRAR_MAPA = True      # Mostrar la imagen con las estrellas marcadas
# =========================================================


def detectar_estrellas(imagen, sistema_wcs):
    """Encuentra estrellas en la imagen y devuelve sus píxeles (x, y) y coordenadas celestes."""
    mascara_nulos = np.isnan(imagen)
    _, fondo_mediana, ruido = sigma_clipped_stats(imagen, sigma=3.0, mask=mascara_nulos)

    buscador = DAOStarFinder(fwhm=TAMANO_ESTRELLA, threshold=UMBRAL_SIGMA * ruido)
    tabla = buscador(np.nan_to_num(imagen - fondo_mediana), mask=mascara_nulos)

    if tabla is None:
        raise SystemExit("No se detectaron estrellas. Intenta bajar UMBRAL_SIGMA.")

    # Extraer posiciones en píxeles (compatible con distintas versiones de photutils)
    col_x = "xcentroid" if "xcentroid" in tabla.colnames else "x_centroid"
    col_y = "ycentroid" if "ycentroid" in tabla.colnames else "y_centroid"
    x, y = np.asarray(tabla[col_x]), np.asarray(tabla[col_y])

    coordenadas = sistema_wcs.pixel_to_world(x, y)
    return x, y, coordenadas


def identificar_en_simbad(coordenadas):
    """Busca el nombre astronómico de cada coordenada en la base de datos SIMBAD."""
    nombres = []
    for coord in coordenadas:
        resultado = Simbad.query_region(coord, radius=RADIO_BUSQUEDA * u.arcsec)
        if resultado is None or len(resultado) == 0:
            nombres.append("Desconocido")
            continue

        # Compatibilidad entre versiones antiguas y nuevas de astroquery
        col_ra = "ra" if "ra" in resultado.colnames else "RA"
        col_dec = "dec" if "dec" in resultado.colnames else "DEC"
        col_id = "main_id" if "main_id" in resultado.colnames else "MAIN_ID"

        unidad = (u.deg, u.deg) if col_ra == "ra" else (u.hourangle, u.deg)
        candidatos = SkyCoord(resultado[col_ra], resultado[col_dec], unit=unidad)

        mas_cercano = coord.separation(candidatos).argmin()
        nombres.append(str(resultado[col_id][mas_cercano]))

    return nombres


def explicar_conversion_wcs(wcs, x, y):
    """Muestra paso a paso cómo se transforma un píxel (x, y) a coordenadas RA/Dec."""
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


if __name__ == "__main__":
    # 1. Leer archivo FITS de una sola vez
    with fits.open(RUTA_FITS) as archivo:
        imagen = archivo[EXTENSION].data
        wcs = WCS(archivo[EXTENSION].header)

    # 2. Detectar e identificar estrellas
    x, y, coords = detectar_estrellas(imagen, wcs)
    nombres = identificar_en_simbad(coords)

    # 3. Mostrar explicación matemática de una estrella de ejemplo
    idx = min(INDICE_EJEMPLO, len(x) - 1)
    explicar_conversion_wcs(wcs, x[idx], y[idx])

    # 4. Imprimir tabla limpia de resultados
    print(f"Total de estrellas detectadas: {len(x)}")
    print(f"{'#':>3} | {'Píxel X':>7} | {'Píxel Y':>7} | {'RA (grados)':>11} | {'Dec (grados)':>12} | Nombre en SIMBAD")
    print("-" * 72)
    for i, (px, py, c, nombre) in enumerate(zip(x, y, coords, nombres)):
        print(f"{i:3d} | {px:7.1f} | {py:7.1f} | {c.ra.deg:11.5f} | {c.dec.deg:12.5f} | {nombre}")

    # 5. Graficar con coordenadas astronómicas reales en los ejes
    if MOSTRAR_MAPA:
        vmin, vmax = np.nanpercentile(imagen, [5, 99])
        plt.figure(figsize=(8, 8))
        ax = plt.subplot(projection=wcs)
        ax.imshow(imagen, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
        ax.scatter(x, y, s=70, facecolors="none", edgecolors="red", label="Estrellas detectadas")
        ax.set_xlabel("Ascensión Recta (RA)")
        ax.set_ylabel("Declinación (Dec)")
        ax.legend()
        plt.show()