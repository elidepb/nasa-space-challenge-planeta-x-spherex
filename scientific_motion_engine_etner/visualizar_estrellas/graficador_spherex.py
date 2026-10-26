# Archivo: graficador_spherex.py
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Circle
from astropy.wcs import WCS
from astropy.nddata import Cutout2D
from astropy.visualization import (
    ZScaleInterval,
    AsinhStretch,
    ImageNormalize
)


class VisualizadorEstelarSPHEREx:
    """
    Módulo de visualización astronómica para graficar imágenes FITS de SPHEREx
    mostrando la foto original, la ubicación exacta de las estrellas detectadas,
    galería de recortes (Cutouts) y un panel de producto final integrado.
    """

    def __init__(self, imagen: np.ndarray, wcs: WCS = None, header=None):
        self.imagen = imagen
        self.wcs = wcs
        self.header = header
        self.colores = {
            'SIMBAD': '#00ffcc',         # Cian brillante para estrellas con nombre clásico
            'Gaia DR3': '#ffdd00',       # Amarillo para estrellas de Gaia DR3
            'Sin catalogar': '#ff5555'   # Rojo para posibles transitorios / objetos no catalogados
        }

    def _obtener_normalizacion(self, datos: np.ndarray):
        """Calcula la normalización ZScale + Asinh de la foto original."""
        datos_validos = datos[np.isfinite(datos)]
        if len(datos_validos) == 0:
            return None
        return ImageNormalize(
            datos_validos,
            interval=ZScaleInterval(contrast=0.20),
            stretch=AsinhStretch(a=0.1)
        )

    def _preparar_coordenadas(self, df_estrellas: pd.DataFrame) -> pd.DataFrame:
        """
        Asegura que el DataFrame tenga tanto coordenadas en píxeles (x_pix, y_pix)
        como coordenadas celestes (ra_deg, dec_deg) usando el WCS de la foto original.
        """
        if df_estrellas is None or df_estrellas.empty:
            return df_estrellas

        df = df_estrellas.copy()

        # Si faltan píxeles pero hay RA/Dec y tenemos WCS, convertir a píxeles de la foto original
        if ('x_pix' not in df.columns or 'y_pix' not in df.columns) and self.wcs is not None:
            if 'ra_deg' in df.columns and 'dec_deg' in df.columns:
                x, y = self.wcs.world_to_pixel_values(df['ra_deg'].values, df['dec_deg'].values)
                df['x_pix'] = x
                df['y_pix'] = y

        # Si faltan RA/Dec pero hay píxeles y tenemos WCS, calcular RA/Dec
        if ('ra_deg' not in df.columns or 'dec_deg' not in df.columns) and self.wcs is not None:
            if 'x_pix' in df.columns and 'y_pix' in df.columns:
                ra, dec = self.wcs.pixel_to_world_values(df['x_pix'].values, df['y_pix'].values)
                df['ra_deg'] = ra
                df['dec_deg'] = dec

        return df

    def _dibujar_ubicaciones(self, ax, df: pd.DataFrame, max_etiquetas: int = 25, mostrar_coords: bool = True):
        """Sobrepone los marcadores de ubicación y etiquetas sobre el eje de la foto original."""
        if df is None or df.empty:
            return

        # 1. Dibujar anillos y miras sobre todas las estrellas detectadas
        for origen, grupo in df.groupby('catalogo_origen'):
            color_c = self.colores.get(origen, 'white')
            ax.scatter(
                grupo['x_pix'],
                grupo['y_pix'],
                s=200,
                facecolors='none',
                edgecolors=color_c,
                linewidths=1.8,
                label=f"{origen} ({len(grupo)})",
                zorder=4
            )
            ax.scatter(
                grupo['x_pix'],
                grupo['y_pix'],
                s=18,
                color=color_c,
                marker='+',
                linewidths=1.2,
                zorder=5
            )

        # 2. Etiquetar las estrellas principales con nombre y ubicación en la imagen
        df_top = df.head(max_etiquetas)
        for idx, (_, fila) in enumerate(df_top.iterrows(), start=1):
            color_txt = self.colores.get(fila.get('catalogo_origen', ''), 'white')
            x, y = fila['x_pix'], fila['y_pix']

            nombre = fila.get('nombre_estrella', f'Estrella #{idx}')
            etiqueta = f"[{idx}] {nombre}"
            if 'magnitud_ref' in fila and pd.notna(fila['magnitud_ref']):
                etiqueta += f" (mag {fila['magnitud_ref']:.1f})"
            if mostrar_coords:
                etiqueta += f"\nPos: X={x:.1f}, Y={y:.1f}"

            ax.annotate(
                etiqueta,
                xy=(x, y),
                xytext=(x + 18, y + 18),
                color=color_txt,
                fontsize=8,
                weight='bold',
                bbox=dict(boxstyle="round,pad=0.25", fc="black", ec=color_txt, alpha=0.75),
                arrowprops=dict(arrowstyle="->", color=color_txt, lw=1.0),
                zorder=6
            )

    def graficar_mapa_anotado(
        self,
        df_estrellas: pd.DataFrame,
        max_etiquetas: int = 25,
        cmap: str = 'magma',
        mostrar_comparativa_original: bool = True,
        guardar_ruta: str = None
    ):
        """
        Muestra la foto original intacta junto a la foto original con las estrellas
        ubicadas y etiquetadas para que el usuario vea dónde se encuentra cada una.
        """
        df = self._preparar_coordenadas(df_estrellas)
        norm = self._obtener_normalizacion(self.imagen)
        proyeccion = self.wcs if self.wcs is not None else None

        if mostrar_comparativa_original:
            fig = plt.figure(figsize=(18, 8.5), dpi=120)
            ax_orig = fig.add_subplot(1, 2, 1, projection=proyeccion)
            ax_anot = fig.add_subplot(1, 2, 2, projection=proyeccion)

            # Panel 1: Foto original limpia
            ax_orig.imshow(self.imagen, origin='lower', cmap=cmap, norm=norm)
            ax_orig.set_title("1. Foto Original (Sin Anotaciones)", fontsize=12, weight='bold', pad=10)
            ax_orig.set_xlabel("Ascensión Recta / X (píxeles)", fontsize=10)
            ax_orig.set_ylabel("Declinación / Y (píxeles)", fontsize=10)
            ax_orig.grid(color='white', ls=':', alpha=0.3)

            # Panel 2: Foto original con ubicación de estrellas
            im = ax_anot.imshow(self.imagen, origin='lower', cmap=cmap, norm=norm)
            self._dibujar_ubicaciones(ax_anot, df, max_etiquetas=max_etiquetas)
            ax_anot.set_title("2. Ubicación de Estrellas en Foto Original", fontsize=12, weight='bold', pad=10)
            ax_anot.set_xlabel("Ascensión Recta / X (píxeles)", fontsize=10)
            ax_anot.set_ylabel("Declinación / Y (píxeles)", fontsize=10)
            ax_anot.grid(color='white', ls=':', alpha=0.35)
            ax_anot.legend(loc='upper right', facecolor='black', edgecolor='white', labelcolor='white')
        else:
            fig = plt.figure(figsize=(12, 11), dpi=120)
            ax_anot = fig.add_subplot(111, projection=proyeccion)
            im = ax_anot.imshow(self.imagen, origin='lower', cmap=cmap, norm=norm)
            self._dibujar_ubicaciones(ax_anot, df, max_etiquetas=max_etiquetas)
            ax_anot.set_xlabel("Ascensión Recta (ICRS / J2000)", fontsize=11)
            ax_anot.set_ylabel("Declinación (ICRS / J2000)", fontsize=11)
            ax_anot.grid(color='white', ls=':', alpha=0.35)
            ax_anot.legend(loc='upper right', facecolor='black', edgecolor='white', labelcolor='white')

        cbar = plt.colorbar(im, ax=ax_anot, fraction=0.046, pad=0.04)
        cbar.set_label("Brillo Superficial Neto (MJy / sr)", fontsize=10)

        detector_info = self.header.get('DETECTOR', 'SPHEREx') if self.header else 'SPHEREx'
        obs_id = self.header.get('OBS_ID', '') if self.header else ''
        plt.suptitle(
            f"Carta de Identificación Estelar - Detector {detector_info} {obs_id}",
            fontsize=14,
            weight='bold',
            y=0.98
        )

        plt.tight_layout()
        if guardar_ruta:
            plt.savefig(guardar_ruta, dpi=200, bbox_inches='tight')
            print(f"Mapa guardado en: {guardar_ruta}")
        plt.show()

    def graficar_galeria_recortes(
        self,
        df_estrellas: pd.DataFrame,
        num_estrellas: int = 9,
        tamano_recorte_pix: int = 36,
        cmap: str = 'viridis',
        guardar_ruta: str = None
    ):
        """
        Genera una cuadrícula haciendo zoom (Cutout2D) sobre las estrellas identificadas
        en la foto original para inspeccionar su PSF, píxel exacto y datos de catálogo.
        """
        df = self._preparar_coordenadas(df_estrellas)
        if df is None or df.empty:
            print("El DataFrame de estrellas está vacío.")
            return

        seleccion = df.head(num_estrellas)
        n = len(seleccion)
        cols = min(3, n)
        filas = int(np.ceil(n / cols))

        fig, axes = plt.subplots(filas, cols, figsize=(4.6 * cols, 4.3 * filas), dpi=120)
        axes = np.atleast_1d(axes).flatten()

        for idx, (_, est) in enumerate(seleccion.iterrows()):
            ax = axes[idx]
            posicion_xy = (est['x_pix'], est['y_pix'])

            cutout = Cutout2D(
                self.imagen,
                position=posicion_xy,
                size=(tamano_recorte_pix, tamano_recorte_pix),
                wcs=self.wcs,
                mode='partial',
                fill_value=np.nan
            )

            sub_img = cutout.data
            norm = self._obtener_normalizacion(sub_img)
            ax.imshow(sub_img, origin='lower', cmap=cmap, norm=norm)

            # Marcar el centro exacto de la estrella en el recorte
            cx, cy = cutout.to_cutout_position(posicion_xy)
            color_est = self.colores.get(est.get('catalogo_origen', ''), 'cyan')
            ax.axvline(cx, color=color_est, ls='--', lw=0.9, alpha=0.85)
            ax.axhline(cy, color=color_est, ls='--', lw=0.9, alpha=0.85)
            ax.scatter([cx], [cy], s=130, facecolors='none', edgecolors=color_est, lw=1.6)

            ra_val = est.get('ra_deg', np.nan)
            dec_val = est.get('dec_deg', np.nan)
            ra_str = f"{ra_val:.3f}°" if pd.notna(ra_val) else "N/A"
            dec_str = f"{dec_val:.3f}°" if pd.notna(dec_val) else "N/A"

            ax.set_title(
                f"[{idx + 1}] {est.get('nombre_estrella', 'Estrella')}\n"
                f"Tipo: {est.get('tipo_objeto', 'N/A')} | Cat: {est.get('catalogo_origen', 'N/A')}\n"
                f"X={est['x_pix']:.1f}, Y={est['y_pix']:.1f} | "
                f"RA={ra_str}, Dec={dec_str}",
                fontsize=8.5
            )

        for j in range(n, len(axes)):
            axes[j].axis('off')

        plt.suptitle(
            "Galería de Estrellas Identificadas en Foto Original (Cutouts)",
            fontsize=13,
            weight='bold',
            y=1.02
        )
        plt.tight_layout()
        if guardar_ruta:
            plt.savefig(guardar_ruta, dpi=200, bbox_inches='tight')
            print(f"Galería de recortes guardada en: {guardar_ruta}")
        plt.show()

    def generar_producto_final(
        self,
        df_estrellas: pd.DataFrame,
        num_recortes: int = 6,
        tamano_recorte_pix: int = 36,
        cmap_mapa: str = 'magma',
        cmap_recortes: str = 'viridis',
        guardar_ruta: str = None
    ):
        """
        PRODUCTO FINAL INTEGRADO:
        Genera un dashboard astronómico completo en una sola imagen que contiene:
        - Izquierda: La foto original completa con las estrellas ubicadas y numeradas.
        - Derecha: Zoom individual (Cutout2D) de cada estrella ubicada con sus coordenadas exactas.
        """
        df = self._preparar_coordenadas(df_estrellas)
        if df is None or df.empty:
            print("El DataFrame de estrellas está vacío.")
            return

        fig = plt.figure(figsize=(18, 10), dpi=130, facecolor='#0e0e12')
        gs = GridSpec(2, 5, figure=fig, width_ratios=[1.3, 1.3, 1, 1, 1], wspace=0.28, hspace=0.32)

        # --- PANEL IZQUIERDO: FOTO ORIGINAL CON UBICACIONES ---
        proyeccion = self.wcs if self.wcs is not None else None
        ax_mapa = fig.add_subplot(gs[:, :2], projection=proyeccion)
        ax_mapa.set_facecolor('black')

        norm_mapa = self._obtener_normalizacion(self.imagen)
        im_mapa = ax_mapa.imshow(self.imagen, origin='lower', cmap=cmap_mapa, norm=norm_mapa)

        self._dibujar_ubicaciones(ax_mapa, df, max_etiquetas=num_recortes, mostrar_coords=True)

        ax_mapa.set_title(
            "Foto Original con Ubicación de Estrellas Detectadas",
            color='white', fontsize=13, weight='bold', pad=12
        )
        ax_mapa.set_xlabel("Ascensión Recta / Píxel X", color='white', fontsize=10)
        ax_mapa.set_ylabel("Declinación / Píxel Y", color='white', fontsize=10)
        ax_mapa.tick_params(colors='white')
        ax_mapa.grid(color='white', ls=':', alpha=0.35)
        ax_mapa.legend(loc='upper right', facecolor='black', edgecolor='white', labelcolor='white')

        cbar = plt.colorbar(im_mapa, ax=ax_mapa, fraction=0.046, pad=0.04)
        cbar.set_label("Brillo Superficial Neto (MJy / sr)", color='white', fontsize=9)
        cbar.ax.yaxis.set_tick_params(color='white', labelcolor='white')

        # --- PANEL DERECHO: GALERÍA DE RECORTES (ZOOM A CADA UBICACIÓN) ---
        seleccion = df.head(min(num_recortes, 6))
        posiciones_grid = [(0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4)]

        for idx, (_, est) in enumerate(seleccion.iterrows()):
            fila_g, col_g = posiciones_grid[idx]
            ax_cut = fig.add_subplot(gs[fila_g, col_g])
            ax_cut.set_facecolor('black')

            posicion_xy = (est['x_pix'], est['y_pix'])
            cutout = Cutout2D(
                self.imagen,
                position=posicion_xy,
                size=(tamano_recorte_pix, tamano_recorte_pix),
                wcs=self.wcs,
                mode='partial',
                fill_value=np.nan
            )

            sub_img = cutout.data
            norm_cut = self._obtener_normalizacion(sub_img)
            ax_cut.imshow(sub_img, origin='lower', cmap=cmap_recortes, norm=norm_cut)

            # Retícula exacta en el recorte
            cx, cy = cutout.to_cutout_position(posicion_xy)
            color_est = self.colores.get(est.get('catalogo_origen', ''), '#00ffcc')
            ax_cut.axvline(cx, color=color_est, ls='--', lw=0.9, alpha=0.85)
            ax_cut.axhline(cy, color=color_est, ls='--', lw=0.9, alpha=0.85)
            ax_cut.add_patch(Circle((cx, cy), radius=4.0, fill=False, edgecolor=color_est, lw=1.5))

            ra_txt = f"{est['ra_deg']:.3f}°" if 'ra_deg' in est and pd.notna(est['ra_deg']) else "N/A"
            dec_txt = f"{est['dec_deg']:.3f}°" if 'dec_deg' in est and pd.notna(est['dec_deg']) else "N/A"
            mag_val = est.get('magnitud_ref', np.nan)
            mag_txt = f"{mag_val:.1f}" if pd.notna(mag_val) else "N/A"

            ax_cut.set_title(
                f"[{idx + 1}] {est.get('nombre_estrella', 'Estrella')}\n"
                f"Cat: {est.get('catalogo_origen', 'N/A')} | Mag: {mag_txt}\n"
                f"Foto X={est['x_pix']:.1f}, Y={est['y_pix']:.1f}\n"
                f"RA={ra_txt}, Dec={dec_txt}",
                color=color_est,
                fontsize=8.5,
                weight='bold'
            )
            ax_cut.tick_params(colors='white', labelsize=7)

        # Apagar celdas vacías si hay menos de 6 estrellas
        for j in range(len(seleccion), 6):
            fila_g, col_g = posiciones_grid[j]
            ax_vacio = fig.add_subplot(gs[fila_g, col_g])
            ax_vacio.axis('off')

        detector_info = self.header.get('DETECTOR', 'SPHEREx') if self.header else 'SPHEREx'
        obs_id = self.header.get('OBS_ID', '') if self.header else ''
        plt.suptitle(
            f"REPORTE DE IDENTIFICACIÓN ESTELAR SPHEREx — Detector {detector_info} {obs_id}",
            color='white',
            fontsize=15,
            weight='bold',
            y=0.98
        )

        if guardar_ruta:
            plt.savefig(guardar_ruta, dpi=220, bbox_inches='tight', facecolor=fig.get_facecolor())
            print(f"Producto final exportado en: {guardar_ruta}")

        plt.show()