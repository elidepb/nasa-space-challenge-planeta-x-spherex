# Elide — SPHEREx Data Pipeline

**Programador:** Elide

**Responsabilidad**

Obtener, leer y preparar los datos científicos de SPHEREx.

Este módulo vive solo en `spherex_data_pipeline_elide/`. Entrega observaciones
normalizadas con el contrato `Observation` para que Etner (motor científico) y
Anghelo (API) puedan consumirlas.

## Qué hace el módulo

1. Consulta **todos** los productos SPHEREx de un Quick Release (QR2, QR3, …)
   que cubren una coordenada RA/Dec y un detector (`SPHEREx-D1` … `D6`).
2. Usa NASA/IPAC IRSA (TAP, con SIA como respaldo).
3. Descarga cutouts FITS de esos productos, sin recortar el total por defecto.
4. Abre los MEF con Astropy y extrae IMAGE, FLAGS, VARIANCE, ZODI, WCS espacial,
   longitud de onda, timestamp, detector y metadatos.
5. Aplica una máscara inicial de píxeles inválidos según FLAGS.
6. Recorta la misma región pedida y deja las matrices con la misma forma
   (padding). Eso **no** alinea ni reproyecta: cada frame conserva su WCS.
7. Ordena las observaciones por `timestamp`.
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
`max_observations=None` (todos los productos TAP de ese detector). El dataset
demo no se usa salvo `source="demo"`.

Cada `Observation` expone:

| Campo | Contenido |
| --- | --- |
| `id` | Identificador de la observación |
| `timestamp` | Fecha/hora ISO-8601 del producto |
| `ra`, `dec` | Centro de la región **pedida** (grados), no de una fuente |
| `detector` | Detector SPHEREx (1–6) |
| `wavelength` | λ central del cutout (μm), WCS-WAVE, calidad aproximada |
| `bandwidth` | Δλ en el píxel central (μm) si el MEF la trae |
| `spectral_calibration_source` | Procedencia espectral (`WCS-WAVE` en IRSA) |
| `spectral_calibration_quality` | Siempre `approximate` (no es calibración de precisión) |
| `spectral_unit` | `μm` |
| `image` | Cutout científico enmascarado (NaN = inválido). Incluye zodi |
| `cutout` | IMAGE recortada, **sin** la máscara de FLAGS |
| `fits_source` | Ruta o URL del FITS |
| `metadata` | Incluye `qr`, `bandpass`, origen (`irsa` / `demo`) y `BUNIT` |
| `flags`, `variance`, `zodi` | Extensiones científicas (`zodi` no está restado de `image`) |
| `valid_mask` | `True` donde el píxel es usable |
| `wcs()` | WCS espacial 2D de Astropy (usar este objeto para alinear) |

`size` está en **grados** (lado del cutout pedido a IRSA). `0.05` es un tamaño
usable; `0.02` deja recortes de ~12×12 píxeles, demasiado chicos para
differencing.

La banda (`SPHEREx-D1` … `D6`, o `detector=1..6`) fija **un detector**. No se
mezclan detectores. **No** es una sola longitud de onda: cada detector SPHEREx
tiene filtro variable, así que IRSA puede devolver muchas λ distintas (en D2,
típicamente ~1.1–1.7 μm) y varias visitas en el tiempo. Para comparar movimiento
hay que emparejar productos de λ parecida en visitas distintas, usando
`wavelength`, `bandwidth` y `timestamp`. El demo sí usa una sola λ.

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

Los FITS demo imitan un MEF SPHEREx (misma λ, mismo WCS, 5 épocas, fuentes
fijas y un objeto sintético en movimiento). Solo se cargan con `source="demo"`.
Sirven para desarrollar el motor; no sustituyen el agrupado espectral de IRSA.

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
descargan **todos** los productos TAP de ese detector (no están agrupados por
λ ni por visita).

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

- Consumir el objeto `Observation`, no `to_contract()`: ese dict no lleva
  `variance`, `valid_mask`, `flags`, `zodi` ni WCS.
- Etner recibe `list[Observation]` y debe usar `image`, `variance`,
  `valid_mask` y `wcs()`. Alinear/reproyectar, restar o normalizar `zodi` y
  emparejar por λ/visita es el motor científico, no este pipeline.
- `wcs()` ya es el WCS espacial listo para `reproject`. No hay que reconstruir
  el header FITS a mano.
- Anghelo puede serializar `observation.to_summary()` en la API y guardar las
  matrices por separado (no van en JSON).
- Los cutouts descargados de IRSA se cachean en `data/cache/`.
