# Archivo: identificador_spherex.py
import logging
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Tuple

import astropy.units as u
import numpy as np
import pandas as pd
import requests
from astropy.coordinates import SkyCoord, match_coordinates_sky
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.utils.exceptions import AstropyWarning
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from photutils.detection import DAOStarFinder

warnings.simplefilter("ignore", category=AstropyWarning)
warnings.simplefilter("ignore", category=UserWarning)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(levelname)s: %(message)s"
    )


class IdentificadorEstelarSPHEREx:
    """
    Módulo de identificación, fotometría rápida y astrometría para SPHEREx.

    Mejoras incorporadas:
    - Enmascaramiento de píxeles defectuosos / rayos cósmicos vía extensión FLAGS.
    - Cálculo exacto de centro y FOV esférico libre del bug de discontinuidad RA 0°/360°.
    - Cálculo de SNR local usando la extensión VARIANCE.
    - Consultas concurrentes (paralelas) a SIMBAD TAP (con flujo/magnitud) y Gaia DR3.
    - Cruce astrométrico vectorizado.
    """

    COLUMNAS_SALIDA = [
        "id_deteccion", "nombre_estrella", "catalogo_origen", "tipo_objeto",
        "x_pix", "y_pix", "ra_deg", "dec_deg", "flujo_pico_mjy_sr",
        "snr_pico", "magnitud_ref", "separacion_arcsec"
    ]

    def __init__(self, ruta_fits: str | Path, aplicar_flags: bool = True):
        self.ruta_fits = ruta_fits
        self.aplicar_flags = aplicar_flags

        self.header: Optional[fits.Header] = None
        self.wcs: Optional[WCS] = None
        self.imagen_cruda: Optional[np.ndarray] = None
        self.imagen_limpia: Optional[np.ndarray] = None
        self.zodi: Optional[np.ndarray] = None
        self.varianza: Optional[np.ndarray] = None
        self.flags: Optional[np.ndarray] = None
    
        self._cargar_fits()

    def _cargar_fits(self) -> None:
        """Carga imagen científica, ZODI, VARIANCE, FLAGS y WCS desde el FITS."""
        with fits.open(self.ruta_fits, ignore_missing_end=True) as hdul:
            ext_map = {h.name.upper(): h for h in hdul}

            # 1. Buscar HDU de imagen
            img_hdu = None
            for cand_ext in ("IMAGE", "SCI", "PRIMARY"):
                if cand_ext in ext_map and ext_map[cand_ext].data is not None:
                    img_hdu = ext_map[cand_ext]
                    break
            if img_hdu is None:
                img_hdu = next(
                    (h for h in hdul if h.data is not None and getattr(h.data, "ndim", 0) >= 2),
                    None
                )
            if img_hdu is None:
                raise ValueError(f"No se encontró matriz 2D válida en '{self.ruta_fits}'")

            self.imagen_cruda = np.array(img_hdu.data, dtype=np.float64, copy=True)
            shape_ref = self.imagen_cruda.shape

            # 2. Construir Header combinado y WCS
            self.header = img_hdu.header.copy()
            if hdul[0].header is not None:
                for key, val in hdul[0].header.items():
                    if key not in self.header and key not in ("COMMENT", "HISTORY", ""):
                        self.header[key] = val

            self.wcs = WCS(self.header, naxis=2)

            # 3. Sustracción de luz zodiacal (ZODI)
            if "ZODI" in ext_map and ext_map["ZODI"].data is not None:
                zodi_data = np.asarray(ext_map["ZODI"].data, dtype=np.float64)
                if zodi_data.shape == shape_ref:
                    self.zodi = zodi_data.copy()
                    self.imagen_limpia = self.imagen_cruda - self.zodi
                else:
                    self.imagen_limpia = self.imagen_cruda.copy()
            else:
                self.imagen_limpia = self.imagen_cruda.copy()

            # 4. Cargar Varianza
            for var_ext in ("VARIANCE", "VAR", "UNCERTAINTY", "ERR"):
                if var_ext in ext_map and ext_map[var_ext].data is not None:
                    var_data = np.asarray(ext_map[var_ext].data, dtype=np.float64)
                    if var_data.shape == shape_ref:
                        # Si la extensión es incertidumbre/error lineal, elevar al cuadrado
                        self.varianza = var_data**2 if var_ext in ("UNCERTAINTY", "ERR") else var_data.copy()
                        break

            # 5. Enmascarar píxeles malos usando FLAGS (Rayos cósmicos, saturación, hot pixels)
            if self.aplicar_flags and "FLAGS" in ext_map and ext_map["FLAGS"].data is not None:
                flags_data = np.asarray(ext_map["FLAGS"].data)
                if flags_data.shape == shape_ref:
                    self.flags = flags_data.copy()
                    # Enmascarar píxeles con flags severos (valor != 0) como NaN
                    # Nota: Puedes ajustar la máscara de bits según el diccionario de bits de SPHEREx
                    self.imagen_limpia[self.flags > 0] = np.nan

    def _calcular_geometria_campo(self) -> Tuple[SkyCoord, float]:
        """
        Calcula el centro exacto del detector en el cielo y el radio de cobertura
        en grados, evitando el problema de discontinuidad en RA = 0° / 360°.
        """
        ny, nx = self.imagen_limpia.shape
        centro_sky = self.wcs.pixel_to_world(nx / 2.0, ny / 2.0)

        # Escala de píxel real a partir de la matriz de proyección WCS (grados/píxel)
        try:
            escalas_deg = proj_plane_pixel_scales(self.wcs)
            escala_max_deg = float(np.max(escalas_deg))
        except Exception:
            escala_max_deg = 6.15 / 3600.0  # Escala nominal de SPHEREx (~6.15"/pix)

        radio_diagonal_deg = 0.5 * np.hypot(nx, ny) * escala_max_deg * 1.15
        return centro_sky, max(0.10, float(radio_diagonal_deg))

    def detectar_e_identificar(
        self,
        fwhm_pix: float = 1.8,
        umbral_sigma: float = 8.0,
        max_fuentes: int = 50,
        radio_cruce_arcsec: float = 6.5,
    ) -> pd.DataFrame:
        """
        Detecta fuentes estelares en la imagen limpia y cruza sus posiciones
        celestes con SIMBAD y Gaia DR3 en paralelo.
        """
        # 1. Estimación robusta del fondo astronómico
        mascara_valida = np.isfinite(self.imagen_limpia) & (self.imagen_limpia != 0.0)
        if not np.any(mascara_valida):
            logger.warning("No se encontraron píxeles válidos para análisis.")
            return self._crear_dataframe_vacio()

        _, median_val, std_val = sigma_clipped_stats(
            self.imagen_limpia[mascara_valida], sigma=3.0, maxiters=5
        )
        if std_val <= 0 or not np.isfinite(std_val):
            std_val = 1.0

        # Preparar imagen restando el fondo y reemplazando NaNs por 0 para DAOStarFinder
        imagen_restada = np.where(mascara_valida, self.imagen_limpia - median_val, 0.0)

        # 2. Detección con DAOStarFinder (ajustando sharplo/sharphi para PSF sub-muestreada)
        daofind = DAOStarFinder(
            fwhm=fwhm_pix,
            threshold=umbral_sigma * std_val,
            sharplo=0.15,
            sharphi=1.2
        )
        fuentes = daofind(imagen_restada)

        if fuentes is None or len(fuentes) == 0:
            logger.info(f"Sin detecciones a {umbral_sigma}σ. Reintentando a 4.0σ...")
            daofind = DAOStarFinder(fwhm=fwhm_pix, threshold=4.0 * std_val, sharplo=0.15, sharphi=1.2)
            fuentes = daofind(imagen_restada)

        if fuentes is None or len(fuentes) == 0:
            logger.warning("No se encontraron fuentes puntuales en la imagen.")
            return self._crear_dataframe_vacio()

        xc_col = "x_centroid" if "x_centroid" in fuentes.colnames else "xcentroid"
        yc_col = "y_centroid" if "y_centroid" in fuentes.colnames else "ycentroid"
        x_pix = np.asarray(fuentes[xc_col], dtype=np.float64)
        y_pix = np.asarray(fuentes[yc_col], dtype=np.float64)

        # Flujo pico y SNR local
        ny, nx = self.imagen_limpia.shape
        xi = np.clip(np.round(x_pix).astype(int), 0, nx - 1)
        yi = np.clip(np.round(y_pix).astype(int), 0, ny - 1)
        flujo_pico = self.imagen_limpia[yi, xi]

        if self.varianza is not None:
            ruido_local = np.sqrt(np.where(self.varianza[yi, xi] > 0, self.varianza[yi, xi], std_val**2))
        else:
            ruido_local = np.full_like(flujo_pico, std_val)
        snr_pico = (flujo_pico - median_val) / ruido_local

        # Ordenar por flujo pico descendente y filtrar top N
        orden = np.argsort(-flujo_pico)
        if max_fuentes and max_fuentes > 0:
            orden = orden[:max_fuentes]

        x_pix, y_pix = x_pix[orden], y_pix[orden]
        flujo_pico, snr_pico = flujo_pico[orden], snr_pico[orden]

        # Conversión a coordenadas celestes
        sky_coords = self.wcs.pixel_to_world(x_pix, y_pix)
        ra_deg = sky_coords.ra.deg
        dec_deg = sky_coords.dec.deg
        total_fuentes = len(x_pix)

        # 3. Consultas concurrentes a SIMBAD y Gaia DR3
        centro_sky, radio_busqueda_deg = self._calcular_geometria_campo()
        logger.info(
            f"{total_fuentes} fuentes detectadas. Consultando catálogos "
            f"(Centro RA={centro_sky.ra.deg:.3f}°, Dec={centro_sky.dec.deg:.3f}°, R={radio_busqueda_deg:.3f}°)..."
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_simbad = executor.submit(
                self._consultar_simbad, centro_sky.ra.deg, centro_sky.dec.deg, radio_busqueda_deg
            )
            fut_gaia = executor.submit(
                self._consultar_gaia_dr3, centro_sky.ra.deg, centro_sky.dec.deg, radio_busqueda_deg
            )
            simbad_coords, simbad_df = fut_simbad.result()
            gaia_coords, gaia_df = fut_gaia.result()

        # 4. Asignación astrométrica vectorizada
        nombres = np.array([f"SPX-J{r:07.3f}{d:+07.3f}" for r, d in zip(ra_deg, dec_deg)], dtype=object)
        catalogos = np.full(total_fuentes, "Sin catalogar", dtype=object)
        tipos = np.full(total_fuentes, "Candidato", dtype=object)
        magnitudes = np.full(total_fuentes, np.nan, dtype=np.float64)
        seps_arcsec = np.full(total_fuentes, np.nan, dtype=np.float64)

        # Paso A: Asignar Gaia DR3 primero (menor prioridad)
        if gaia_coords is not None and len(gaia_coords) > 0:
            g_idx, g_sep2d, _ = match_coordinates_sky(sky_coords, gaia_coords)
            g_mask = g_sep2d.arcsec <= radio_cruce_arcsec
            if np.any(g_mask):
                matched_gaia = gaia_df.iloc[g_idx[g_mask]]
                nombres[g_mask] = "Gaia DR3 " + matched_gaia["Source"].astype(str).to_numpy()
                catalogos[g_mask] = "Gaia DR3"
                tipos[g_mask] = "Estrella"
                magnitudes[g_mask] = matched_gaia["Gmag"].to_numpy(dtype=np.float64)
                seps_arcsec[g_mask] = g_sep2d.arcsec[g_mask]

        # Paso B: Sobrescribir con SIMBAD donde exista coincidencia (mayor prioridad)
        if simbad_coords is not None and len(simbad_coords) > 0:
            s_idx, s_sep2d, _ = match_coordinates_sky(sky_coords, simbad_coords)
            s_mask = s_sep2d.arcsec <= radio_cruce_arcsec
            if np.any(s_mask):
                matched_sim = simbad_df.iloc[s_idx[s_mask]]
                nombres[s_mask] = matched_sim["main_id"].astype(str).to_numpy()
                catalogos[s_mask] = "SIMBAD"
                tipos[s_mask] = matched_sim["otype"].astype(str).to_numpy()
                # Si SIMBAD tiene magnitud válida la usamos; si no, conservamos la Gmag de Gaia si existía
                sim_mags = matched_sim["mag"].to_numpy(dtype=np.float64)
                magnitudes[s_mask] = np.where(np.isfinite(sim_mags), sim_mags, magnitudes[s_mask])
                seps_arcsec[s_mask] = s_sep2d.arcsec[s_mask]

        df = pd.DataFrame({
            "id_deteccion": np.arange(1, total_fuentes + 1),
            "nombre_estrella": nombres,
            "catalogo_origen": catalogos,
            "tipo_objeto": tipos,
            "x_pix": np.round(x_pix, 2),
            "y_pix": np.round(y_pix, 2),
            "ra_deg": np.round(ra_deg, 6),
            "dec_deg": np.round(dec_deg, 6),
            "flujo_pico_mjy_sr": np.round(flujo_pico, 3),
            "snr_pico": np.round(snr_pico, 1),
            "magnitud_ref": np.round(magnitudes, 3),
            "separacion_arcsec": np.round(seps_arcsec, 2),
        })

        conteo = df["catalogo_origen"].value_counts().to_dict()
        logger.info(f"Identificación finalizada: {conteo}")
        return df

    @staticmethod
    def _consultar_simbad(ra: float, dec: float, radio_deg: float) -> Tuple[Optional[SkyCoord], pd.DataFrame]:
        """Consulta el TAP de SIMBAD incluyendo magnitudes ópticas/IR (V, G, J, K)."""
        tap_url = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
        adql = f"""
        SELECT TOP 5000 b.main_id, b.ra, b.dec, b.otype,
               f.G, f.V, f.J, f.K
        FROM basic AS b
        LEFT JOIN allfluxes AS f ON b.oid = f.oidref
        WHERE CONTAINS(POINT('ICRS', b.ra, b.dec), CIRCLE('ICRS', {ra:.5f}, {dec:.5f}, {radio_deg:.4f})) = 1
          AND b.ra IS NOT NULL AND b.dec IS NOT NULL
        """
        try:
            r = requests.post(
                tap_url,
                data={"request": "doQuery", "lang": "adql", "format": "json", "query": adql},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            if data:
                df = pd.DataFrame(data, columns=["main_id", "ra", "dec", "otype", "g", "v", "j", "k"])
                for col in ["ra", "dec", "g", "v", "j", "k"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["mag"] = df["g"].combine_first(df["v"]).combine_first(df["j"]).combine_first(df["k"])
                coords = SkyCoord(ra=df["ra"].to_numpy() * u.deg, dec=df["dec"].to_numpy() * u.deg)
                return coords, df
        except Exception as e:
            logger.warning(f"No se pudo consultar SIMBAD TAP: {e}")
        return None, pd.DataFrame()

    @staticmethod
    def _consultar_gaia_dr3(ra: float, dec: float, radio_deg: float) -> Tuple[Optional[SkyCoord], pd.DataFrame]:
        """Consulta Gaia DR3 vía Vizier retornando un DataFrame limpio."""
        try:
            from astroquery.vizier import Vizier

            v = Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag"], row_limit=5000)
            v.TIMEOUT = 15
            c = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
            tables = v.query_region(c, radius=radio_deg * u.deg, catalog="I/355/gaiadr3")
            if tables and len(tables[0]) > 0:
                df = tables[0].to_pandas()
                coords = SkyCoord(
                    ra=df["RA_ICRS"].to_numpy() * u.deg,
                    dec=df["DE_ICRS"].to_numpy() * u.deg
                )
                return coords, df
        except Exception as e:
            logger.warning(f"No se pudo consultar Gaia DR3 en Vizier: {e}")
        return None, pd.DataFrame()

    @classmethod
    def _crear_dataframe_vacio(cls) -> pd.DataFrame:
        return pd.DataFrame(columns=cls.COLUMNAS_SALIDA)