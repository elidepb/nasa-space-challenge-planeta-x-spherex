# Backend API Integration — SPHEREx Planet X

API REST para el procesamiento y análisis de datos espectrales del telescopio SPHEREx dentro del desafío NASA Space Challenge "Planet X".

Conecta los servicios de catálogo y descarga de **Elide**, el motor de detección de movimiento **Etner** y el almacenamiento de sesiones, expuesto a través de FastAPI.

---

## Levantamiento rápido

El servicio se ejecuta en un contenedor Docker. Desde la raíz del monorepo:

```bash
docker compose up --build
```

El `--build` es obligatorio para que se instalen las dependencias actualizadas (`fastapi[standard]`, `reproject`, `matplotlib`, `pyvo`, `astroquery`, etc.).

La API queda disponible en:

```
http://localhost:8000
```

Documentación interactiva automática:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Variables de entorno (`.env`)

Crea un archivo `backend_api_integration_anghelo/.env` con las variables que necesites sobrescribir. Las actuales y sus valores por defecto:

| Variable          | Valor por defecto  | Descripción                                             |
| ----------------- | ------------------ | ------------------------------------------------------- |
| `STORAGE_TYPE`    | `memory`           | Tipo de almacenamiento de sesiones (`memory` o `mongo`) |
| `CACHE_DIR`       | `/app/data/cache`  | Directorio de caché de archivos FITS                    |
| `IMAGES_DIR`      | `/app/data/images` | Directorio de imágenes PNG generadas                    |
| `CACHE_TTL_HOURS` | `24`               | Tiempo de vida del caché en horas                       |

Ejemplo `.env`:

```env
STORAGE_TYPE=memory
CACHE_DIR=/app/data/cache
IMAGES_DIR=/app/data/images
CACHE_TTL_HOURS=24
```

---

## Endpoints

Todas las rutas de la API viven bajo el prefijo **`/api/v1`**.  
El health check vive en la raíz: `GET /health`.

### Flujo general

1. `POST /spectral-analyses` — inicia el análisis espectral (Fase 1). Devuelve un `session_id` inmediatamente. El procesamiento completo (descarga FITS + renderizado previews + análisis Etner) se ejecuta en segundo plano.
2. `GET /spectral-analyses/{session_id}` — consulta el estado y progreso de la sesión.
3. `GET /spectral-analyses/{session_id}/observations` — lista resumen de observaciones (sin matrices).
4. `GET /spectral-analyses/{session_id}/images` — lista URLs de preview PNG y descarga FITS por observación.
5. `GET /spectral-analyses/{session_id}/images/{obs_id}/preview.png` — sirve la imagen PNG.
6. `GET /spectral-analyses/{session_id}/images/{obs_id}/file.fits` — descarga el FITS original.
7. `POST /spectral-analyses/rgb-composite` — genera composición falso color RGB por survey (una imagen por survey común a los 3 canales). No usa `session_id`.
8. `GET /spectral-analyses/rgb-composites/{composite_id}.png` — descarga el PNG de una composición RGB generada.
9. `GET /spectral-analyses/{session_id}/candidates` — candidatos de movimiento detectados por Etner, organizados por pares de surveys consecutivos (solo cuando `estado == COMPLETADO`).
10. `GET /health` — health check del servicio.

---

### 1. Iniciar análisis espectral (Fase 1)

**`POST /spectral-analyses`**  
Cuerpo (`application/json`):

| Campo            | Tipo    | Requerido | Descripción                                | Ejemplo        |
| ---------------- | ------- | --------- | ------------------------------------------ | -------------- |
| `ra`             | `float` | ✅        | Ascensión recta en grados (0–360)          | `180.5`        |
| `dec`            | `float` | ✅        | Declinación en grados (-90–90)             | `45.2`         |
| `size_deg`       | `float` | ✅        | Tamaño del lado del recorte en grados (>0) | `0.5`          |
| `bandpass`       | `str`   | ❌        | Banda/detector SPHEREx                     | `"SPHEREx-D2"` |
| `spectral_group` | `int`   | ❌        | Grupo espectral 1–17                       | `5`            |

Respuesta `202 Accepted` (metadatos rápidos de IRSA, sin descargar FITS):

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "estado": "EN_PROCESO",
  "message": "Consulta iniciada. Procesamiento en segundo plano.",
  "spectral_group": 5,
  "observaciones": [
    {
      "id_exposicion": "level2_2025W23_2B_0206_1D2_spx_l2b-v20-2025-251.fits",
      "timestamp": "2025-06-06 11:22:23.837",
      "survey_index": 1,
      "wavelength": 1.238353,
      "fits_source": "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/2025W23_2B/l2b-v20-2025-251/2/level2_2025W23_2B_0206_1D2_spx_l2b-v20-2025-251.fits"
    }
  ]
}
```

Cada ítem de `observaciones` en esta respuesta rápida incluye:

| Campo           | Tipo    | Descripción                                                |
| --------------- | ------- | ---------------------------------------------------------- |
| `id_exposicion` | `str`   | ID de observación (nombre del archivo en IRSA)             |
| `timestamp`     | `str`   | Fecha/hora de captura                                      |
| `survey_index`  | `int`   | Índice del survey espectral asignado                       |
| `wavelength`    | `float` | Longitud de onda teórica del centro del bin espectral (µm) |
| `fits_source`   | `str`   | URL de acceso al FITS en IRSA (`access_url`, link remoto)  |

> **Nota:** Los campos `shape`, `n_invalid_pixels`, `bandwidth` y el `fits_source` local (ruta del archivo descargado en disco) **no están en esta respuesta rápida**. Se poblan después cuando el background task termina la descarga de FITS; consúltalos con `GET /spectral-analyses/{session_id}/observations` una vez que `estado == COMPLETADO`.

Ejemplo con cURL:

```bash
curl -X POST http://localhost:8000/api/v1/spectral-analyses \
  -H "Content-Type: application/json" \
  -d '{"ra": 180.5, "dec": 45.2, "size_deg": 0.5, "spectral_group": 5}'
```

---

### 2. Consultar estado de sesión

**`GET /spectral-analyses/{session_id}`**

Parámetro de ruta: `session_id` (`UUID`).

Respuesta `200 OK`:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "estado": "COMPLETADO",
  "progreso_porcentaje": 100.0,
  "total_observaciones_grupo": 12,
  "observaciones_descargadas": 12,
  "candidatos_detectados": 3,
  "error_detail": null
}
```

Códigos: `200`, `404` (sesión no encontrada).

---

### 3. Resumen de observaciones (sin matrices)

**`GET /spectral-analyses/{session_id}/observations`**

Devuelve una lista de observaciones con metadatos ligeros:

| Campo              | Tipo                | Descripción                        |
| ------------------ | ------------------- | ---------------------------------- |
| `id_exposicion`    | `str`               | ID de la observación               |
| `timestamp`        | `str`               | Fecha/hora de captura              |
| `survey_index`     | `int`               | Índice del survey al que pertenece |
| `wavelength`       | `float \| null`     | Longitud de onda en µm             |
| `bandwidth`        | `float \| null`     | Ancho de banda                     |
| `fits_source`      | `str`               | Ruta/origen del archivo FITS       |
| `shape`            | `list[int] \| null` | Dimensiones `[alto, ancho]`        |
| `n_invalid_pixels` | `int \| null`       | Pixeles inválidos                  |

---

### 4. Lista de imágenes y URLs de descarga

**`GET /spectral-analyses/{session_id}/images`**

Respuesta `200 OK`:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_imagenes": 12,
  "imagenes": [
    {
      "obs_id": "obs_001",
      "survey_index": 1,
      "wavelength_um": 1.15,
      "shape": [1024, 1024],
      "preview_png_url": "/api/v1/spectral-analyses/{session_id}/images/obs_001/preview.png",
      "fits_download_url": "/api/v1/spectral-analyses/{session_id}/images/obs_001/file.fits"
    }
  ]
}
```

Cada `ImageListItem`:

| Campo               | Tipo        | Descripción                                  |
| ------------------- | ----------- | -------------------------------------------- |
| `obs_id`            | `str`       | ID de observación                            |
| `survey_index`      | `int`       | Índice del sondeo (propio de la observación) |
| `wavelength_um`     | `float`     | Longitud de onda en µm                       |
| `shape`             | `list[int]` | Dimensiones `[alto, ancho]`                  |
| `preview_png_url`   | `str`       | Ruta relativa para ver el PNG                |
| `fits_download_url` | `str`       | Ruta relativa para descargar el FITS         |

---

### 5. Previsualización PNG

**`GET /spectral-analyses/{session_id}/images/{obs_id}/preview.png`**

Parámetros de ruta: `session_id` (`UUID`), `obs_id` (`str`).

Devuelve la imagen PNG con `Content-Type: image/png`.

Códigos: `200`, `404` (preview no encontrada).

Ejemplo:

```bash
curl -O http://localhost:8000/api/v1/spectral-analyses/{session_id}/images/obs_001/preview.png
```

---

### 6. Descarga del FITS original

**`GET /spectral-analyses/{session_id}/images/{obs_id}/file.fits`**

Parámetros de ruta: `session_id` (`UUID`), `obs_id` (`str`).

Devuelve el archivo FITS con `Content-Type: application/fits` y `Content-Disposition: attachment`.

Códigos: `200`, `404` (FITS o sesión no encontrados).

Ejemplo:

```bash
curl -O http://localhost:8000/api/v1/spectral-analyses/{session_id}/images/obs_001/file.fits
```

---

### 7. Composición falso color RGB por survey

**`POST /spectral-analyses/rgb-composite`**

Genera una composición RGB falsa **por survey (época)**: una imagen por survey común a los tres canales. Para cada canal consulta Elide con el detector `SPHEREx-D{sensor}` y el grupo espectral pedido (las 3 llamadas a Elide se hacen en paralelo), agrupa las observaciones en surveys (gaps temporales > 45 días), homogeniza las formas y arma un PNG RGB por survey común. Cada PNG se persiste en el volumen de imágenes.

No usa `session_id`.

Cuerpo (`application/json`):

| Campo       | Tipo     | Requerido | Descripción                                            | Ejemplo       |
| ----------- | -------- | --------- | ------------------------------------------------------ | ------------- |
| `ra`        | `float`  | ✅        | Ascensión recta en grados (0–360)                      | `210.80227`   |
| `dec`       | `float`  | ✅        | Declinación en grados (-90–90)                         | `54.34895`    |
| `size_deg`  | `float`  | ❌        | Tamaño del lado del recorte en grados (>0, default 0.85) | `0.85`        |
| `channels`  | `array`  | ✅        | Definición de canales RGB (1 a 3)                      | ver abajo     |

Cada ítem de `channels`:

| Campo      | Tipo     | Requerido | Descripción                          | Ejemplo |
| ---------- | -------- | --------- | ------------------------------------ | ------- |
| `channel`  | `str`    | ✅        | Color: `"red"`, `"green"` o `"blue"` | `"red"` |
| `sensor`   | `int`    | ✅        | Número de detector SPHEREx (1–6)     | `2`     |
| `group`    | `int`    | ✅        | Grupo espectral (1–17)               | `5`     |

Respuesta `200 OK`:

```json
{
  "total_surveys": 3,
  "composites": [
    {
      "survey_index": 1,
      "epoch": "2025-05-24T21:56:50",
      "composite_id": "rgb_s1_d2g5_d4g5_d6g5",
      "image_url": "/api/v1/spectral-analyses/rgb-composites/rgb_s1_d2g5_d4g5_d6g5.png",
      "channels_used": {
        "red_obs_id": "2025W21_2C_0401_3",
        "green_obs_id": "2025W21_2C_0401_4",
        "blue_obs_id": "2025W22_1B_0129_1"
      }
    }
  ]
}
```

Códigos: `200`, `400` (canal faltante o sin observaciones para un canal).

Ejemplo con cURL:

```bash
curl -X POST http://localhost:8000/api/v1/spectral-analyses/rgb-composite \
  -H "Content-Type: application/json" \
  -d '{"ra": 210.80227, "dec": 54.34895, "size_deg": 0.85, "channels": [{"channel": "red", "sensor": 2, "group": 5}, {"channel": "green", "sensor": 4, "group": 5}, {"channel": "blue", "sensor": 6, "group": 5}]}'
```

---

### 8. Descarga de composición RGB (PNG)

**`GET /spectral-analyses/rgb-composites/{composite_id}.png`**

Devuelve el archivo PNG de una composición RGB generada por `POST /rgb-composite`.

Parámetro de ruta: `composite_id` (`str`, viene en `composites[].composite_id` de la respuesta del POST).

Devuelve la imagen PNG con `Content-Type: image/png` y `Cache-Control: public, max-age=86400, immutable`.

Ejemplo:

```bash
curl -O http://localhost:8000/api/v1/spectral-analyses/rgb-composites/rgb_s1_d2g5_d4g5_d6g5.png
```

Códigos: `200`, `404` (PNG no encontrado).

---

### 9. Candidatos de movimiento (Etner)

**`GET /spectral-analyses/{session_id}/candidates`**

Parámetros de ruta: `session_id` (`UUID`).

Solo disponible cuando `estado == COMPLETADO`.

Devuelve candidatos organizados por pares de surveys consecutivos en paralelo:

| Campo              | Tipo    | Descripción                            |
| ------------------ | ------- | -------------------------------------- |
| `session_id`       | `str`   | ID de sesión                           |
| `total_candidatos` | `int`   | Total de candidatos en todos los pares |
| `pairs`            | `array` | Lista de pares de surveys              |

Cada `pair`:

| Campo              | Tipo         | Descripción                             |
| ------------------ | ------------ | --------------------------------------- |
| `survey_pair`      | `array[int]` | Par de surveys analizados, ej. `[1, 2]` |
| `total_candidatos` | `int`        | Candidatos en este par                  |
| `candidatos`       | `array`      | Lista de candidatos                     |

Cada candidato:

| Campo              | Tipo    | Descripción                              |
| ------------------ | ------- | ---------------------------------------- |
| `candidate_id`     | `str`   | Identificador del candidato              |
| `ra`               | `float` | Ascensión recta                          |
| `dec`              | `float` | Declinación                              |
| `snr`              | `float` | Signal-to-noise ratio                    |
| `motion_arcsec_yr` | `float` | Movimiento en arcsegundos por año        |
| `status`           | `str`   | Estado del candidato (ej. `"VALIDATED"`) |

Ejemplo con 3 surveys:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_candidatos": 5,
  "pairs": [
    {
      "survey_pair": [1, 2],
      "total_candidatos": 3,
      "candidatos": [
        {
          "candidate_id": "cand_001",
          "ra": 180.55,
          "dec": 45.25,
          "snr": 12.4,
          "motion_arcsec_yr": 0.85,
          "status": "VALIDATED"
        }
      ]
    },
    {
      "survey_pair": [2, 3],
      "total_candidatos": 2,
      "candidatos": []
    }
  ]
}
```

Códigos: `200`, `400` (estado no completado), `404` (sesión no encontrada).

---

### 10. Health check

**`GET /health`** (sin prefijo `/api/v1`)

Respuesta:

```json
{
  "status": "ok",
  "storage_type": "memory"
}
```

---

## Notas importantes

- La sesión se procesa en segundo plano (`BackgroundTasks`). Después de `POST /spectral-analyses`, el estado empieza como `"EN_PROCESO"` y pasa a `"COMPLETADO"` cuando termina la Fase 2 (descarga FITS, renderizado de previews, análisis Etner).
- Los candidatos de movimiento solo están disponibles una vez `estado == COMPLETADO`.
- Los candidatos se analizan por pares de surveys consecutivos en paralelo: 3 surveys generan pares (1,2) y (2,3); 4 surveys generan (1,2), (2,3) y (3,4).
- El endpoint `rgb-composite` genera una imagen RGB por survey y no requiere `session_id`.
- El almacenamiento puede ser en memoria o Mongo según `STORAGE_TYPE`.
- Los endpoints de imagen y FITS leen de los volúmenes de datos configurados (`IMAGES_DIR` y `CACHE_DIR`).
