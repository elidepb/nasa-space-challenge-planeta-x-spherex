# Elide — SPHEREx Data Pipeline

**Programador:** Elide

**Responsabilidad**

Obtener, leer y preparar los datos científicos de SPHEREx.

**Tareas**

1. Implementar consulta de observaciones SPHEREx disponibles para una coordenada RA/Dec.
2. Utilizar NASA/IPAC IRSA como fuente de datos.
3. Recuperar observaciones correspondientes a diferentes épocas.
4. Descargar FITS completos o solicitar cutouts FITS.
5. Abrir archivos FITS mediante Python y Astropy.
6. Extraer:
   - IMAGE;
   - FLAGS;
   - VARIANCE;
   - ZODI;
   - WCS;
   - wavelength;
   - timestamp;
   - detector;
   - metadatos relevantes.
7. Aplicar máscara inicial de píxeles inválidos según FLAGS.
8. Generar cutouts homogéneos de una misma región.
9. Organizar observaciones cronológicamente.
10. Crear un dataset local de demostración con varias épocas de una misma región.
11. Entregar los datos usando el contrato `Observation`.

**Interfaz esperada**

```python
get_observations(
    ra,
    dec,
    size
) -> list[Observation]
```

**Entregables**

- módulo Python de acceso a SPHEREx;
- descarga automatizada de cutouts;
- lectura correcta de FITS;
- dataset demo;
- lista normalizada de observaciones;
- documentación de ejecución del módulo.
