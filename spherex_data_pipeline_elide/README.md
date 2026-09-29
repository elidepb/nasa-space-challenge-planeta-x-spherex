# Elide — SPHEREx Data Pipeline

**Programador:** Elide

**Responsabilidad**

Obtener, leer y preparar los datos científicos de SPHEREx.

Este módulo vive solo en `spherex_data_pipeline_elide/`. Entrega observaciones
normalizadas con el contrato `Observation` para que Etner (motor científico) y
Anghelo (API) puedan consumirlas.

## Qué hace el módulo

1. Consulta **todas** las épocas SPHEREx disponibles en un Quick Release
   (QR2, QR3, …) para una coordenada RA/Dec y una banda/detector.
2. Usa NASA/IPAC IRSA (TAP, con SIA como respaldo).
3. Descarga cutouts FITS de esas épocas, sin recortar el total por defecto.
4. Abre los MEF con Astropy y extrae IMAGE, FLAGS, VARIANCE, ZODI, WCS,
   longitud de onda, timestamp, detector y metadatos.
5. Aplica una máscara inicial de píxeles inválidos según FLAGS.
6. Recorta la misma región y homogeniza las formas de las matrices.
7. Ordena las observaciones cronológicamente.
8. Incluye un dataset demo local, **solo si se pide** `source="demo"`.

## Interfaz

```python
from spherex_pipeline import get_observations

observations = get_observations(
    ra,
    dec,
    size,
    qr="qr2",
    bandpass="SPHEREx-D2",
)
```

Por defecto: `source="irsa"`, `qr="qr2"`, `bandpass="SPHEREx-D2"` y
`max_observations=None` (todas las épocas TAP). El dataset demo no se usa
salvo `source="demo"`.

Cada `Observation` expone:

| Campo | Contenido |
| --- | --- |
| `id` | Identificador de la observación |
| `timestamp` | Fecha/hora ISO-8601 de esa época |
| `ra`, `dec` | Centro de la región (grados) |
| `detector` | Detector SPHEREx (1–6) |
| `wavelength` | λ central del cutout (μm), WCS-WAVE, calidad aproximada |
| `bandwidth` | Δλ en el píxel central (μm) si el MEF la trae |
| `spectral_calibration_source` | Procedencia espectral (`WCS-WAVE` en IRSA) |
| `spectral_calibration_quality` | Siempre `approximate` (no es calibración de precisión) |
| `spectral_unit` | `μm` |
| `image` | Cutout científico enmascarado (NaN = inválido) |
| `cutout` | Cutout IMAGE original |
| `fits_source` | Ruta o URL del FITS |
| `metadata` | Incluye `qr`, `bandpass` y origen (`irsa` / `demo`) |
| `flags`, `variance`, `zodi` | Extensiones científicas |
| `valid_mask` | `True` donde el píxel es usable |
| `wcs()` | WCS espacial de Astropy |

`size` está en **grados** (lado del cutout pedido a IRSA).

La banda es explícita (`SPHEREx-D1` … `SPHEREx-D6`, o `detector=1..6`) para
comparar épocas en la misma λ. No se mezclan detectores.

## Instalación

Desde esta carpeta:

```bash
cd spherex_data_pipeline_elide
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Dataset demo

La región demo es M101 (Pinwheel):

- RA = `210.80227`
- Dec = `54.34895`
- size = `0.05` deg
- qr = `qr2`
- bandpass = `SPHEREx-D2`

Los FITS demo imitan un MEF SPHEREx. Solo se cargan con `source="demo"`.

```bash
python -m spherex_pipeline --build-demo
python -m spherex_pipeline --source demo --qr qr2 --bandpass SPHEREx-D2
```

## Ejecución IRSA (camino por defecto)

```bash
python -m spherex_pipeline --ra 210.80227 --dec 54.34895 --size 0.05 --qr qr2 --bandpass SPHEREx-D2 -v
```

Equivalente en Python:

```python
from spherex_pipeline import get_observations

obs = get_observations(210.80227, 54.34895, 0.05, qr="qr2", bandpass="SPHEREx-D2")
print(len(obs), obs[0].timestamp, obs[0].wavelength)
```

Un entero en `--max-observations` es un tope opcional. Sin ese flag se
descargan **todas** las épocas encontradas.

## Tests

```bash
pytest
python -m spherex_pipeline.acceptance
```

La prueba de aceptación usa IRSA real (QR2, SPHEREx-D2, M101). El éxito es
`TAP matches == Observation entregados`, no un 84 fijo.

```text
wavelength/bandwidth:
    derivados de WCS-WAVE
    unidad: μm
    calidad: aproximada

QR:
    el release se selecciona explícitamente
    ausencia de datos en un QR no implica error del pipeline

source=irsa:
    nunca utiliza automáticamente el dataset demo

source=demo:
    únicamente datos sintéticos para desarrollo/tests
```

## Notas para el resto del equipo

- Etner debe recibir `list[Observation]` y usar `image`, `variance`, `valid_mask` y `wcs()`.
- Anghelo puede serializar `observation.to_summary()` en la API y guardar las
  matrices por separado (no van en JSON).
- Los cutouts descargados de IRSA se cachean en `data/cache/`.
