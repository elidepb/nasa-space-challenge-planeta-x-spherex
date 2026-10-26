# Archivo: main.py
import sys
from pathlib import Path

from identificador_spherex import IdentificadorEstelarSPHEREx
from graficador_spherex import VisualizadorEstelarSPHEREx

# 1. Configuración de rutas (resueltas dinámicamente respecto a este archivo)
BASE_DIR = Path(__file__).resolve().parent
ruta_mi_fits = (
    BASE_DIR.parent
    / "spherex_6_bandas"
    / "level2_2025W19_2B_0103_4D1_spx_l2b-v20-2025-247.fits"
)

# Carpeta donde se guardarán las imágenes y el CSV del producto final
DIR_SALIDA = BASE_DIR / "resultados_spherex"
DIR_SALIDA.mkdir(parents=True, exist_ok=True)


def main():
    # Verificar que el archivo FITS exista antes de procesar
    if not ruta_mi_fits.exists():
        print(f"[ERROR] No se encontró el archivo FITS en:\n  -> {ruta_mi_fits}")
        sys.exit(1)

    print(f"[1/3] Procesando archivo FITS: {ruta_mi_fits.name} ...")

    # 2. Ejecutar Módulo 1: Cargar, limpiar ZODI, detectar estrellas y obtener sus nombres
    identificador = IdentificadorEstelarSPHEREx(str(ruta_mi_fits))
    tabla_estrellas = identificador.detectar_e_identificar(
        fwhm_pix=2.5,           # Ancho típico de PSF en SPHEREx (~2 a 3 píxeles)
        umbral_sigma=10.0,      # Detectar fuentes con señal > 10 veces el ruido de fondo
        max_fuentes=50,         # Identificar las 50 estrellas más brillantes del campo
        radio_cruce_arcsec=6.2  # 1 píxel de SPHEREx mide ~6.15 arcsec
    )

    if tabla_estrellas is None or tabla_estrellas.empty:
        print("[AVISO] No se detectaron estrellas con los parámetros actuales.")
        sys.exit(0)

    # Mostrar en consola solo las columnas disponibles para evitar KeyError
    columnas_deseadas = [
        'id_deteccion', 'nombre_estrella', 'catalogo_origen',
        'tipo_objeto', 'x_pix', 'y_pix', 'ra_deg', 'dec_deg', 'flujo_pico_mjy_sr'
    ]
    columnas_presentes = [c for c in columnas_deseadas if c in tabla_estrellas.columns]

    print("\n=== TABLA DE ESTRELLAS IDENTIFICADAS ===")
    print(tabla_estrellas[columnas_presentes].to_string(index=False))

    # Guardar el catálogo identificado en CSV
    ruta_csv = DIR_SALIDA / "estrellas_identificadas_spherex.csv"
    tabla_estrellas.to_csv(ruta_csv, index=False, encoding="utf-8")
    print(f"\n[OK] Catálogo exportado en: {ruta_csv}")

    # 3. Ejecutar Módulo 2: Visualizar sobre la foto original
    # Si tu identificador guarda la foto cruda como .imagen_original o .imagen_raw la usa;
    # de lo contrario utiliza .imagen_limpia.
    foto_base = getattr(
        identificador, 'imagen_original',
        getattr(identificador, 'imagen_raw', identificador.imagen_limpia)
    )

    print("[2/3] Generando mapas de ubicación sobre la foto original...")
    visualizador = VisualizadorEstelarSPHEREx(
        imagen=foto_base,
        wcs=identificador.wcs,
        header=identificador.header
    )

    # Vista 1: Comparativa lado a lado (Foto Original Limpia vs. Foto Original con Ubicaciones)
    visualizador.graficar_mapa_anotado(
        df_estrellas=tabla_estrellas,
        max_etiquetas=20,
        mostrar_comparativa_original=True,
        guardar_ruta=str(DIR_SALIDA / "1_mapa_estrellas_spherex.png")
    )

    # Vista 2: Cuadrícula de recortes (zoom 36x36 px a las 9 estrellas más brillantes)
    visualizador.graficar_galeria_recortes(
        df_estrellas=tabla_estrellas,
        num_estrellas=9,
        tamano_recorte_pix=36,
        guardar_ruta=str(DIR_SALIDA / "2_galeria_recortes_spherex.png")
    )

    # Vista 3 (PRODUCTO FINAL): Dashboard unificado (Foto original anotada + 6 recortes numerados)
    print("[3/3] Generando lámina de producto final...")
    visualizador.generar_producto_final(
        df_estrellas=tabla_estrellas,
        num_recortes=6,
        tamano_recorte_pix=36,
        guardar_ruta=str(DIR_SALIDA / "3_producto_final_spherex.png")
    )


if __name__ == "__main__":
    main()