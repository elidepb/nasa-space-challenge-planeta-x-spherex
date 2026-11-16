# API Frontend — Backend SPHEREx Planet X

Base URL: `http://localhost:8000/api/v1`

Sin autenticación. Todos los cuerpos son `application/json`.  
Cada endpoint documenta **entrada**, **salida exitosa** y **códigos de error**.

---

## 1. Iniciar análisis espectral (Fase 1)

**`POST /spectral-analyses`**

Inicia el análisis espectral y encola el procesamiento en segundo plano. Devuelve inmediatamente un `session_id`.

### Entrada

| Campo | Tipo | Requerido | Descripción | Ejemplo |
|-------|------|-----------|-------------|---------|
| `ra` | `number` | Sí | Ascensión recta en grados (0–360) | `180.5` |
| `dec` | `number` | Sí | Declinación en grados (-90–90) | `45.2` |
| `size_deg` | `number` | Sí | Tamaño del lado del recorte en grados (>0) | `0.5` |
| `bandpass` | `string` | No | Banda/detector SPHEREx | `"SPHEREx-D2"` |
| `spectral_group` | `integer` | No | Grupo espectral 1–17 | `5` |

### Salida exitosa (`202 Accepted`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `session_id` | `string` (UUID) | Identificador de la sesión |
| `estado` | `string` | `"EN_PROCESO"` |
| `message` | `string` | Mensaje de estado |
| `spectral_group` | `integer` | Grupo espectral usado |
| `observaciones` | `array` | Lista de metadatos de observaciones (vacía al iniciar) |

Cada ítem de `observaciones` (metadatos rápidos de IRSA, sin descargar FITS):

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_exposicion` | `string` | ID de observación (nombre del archivo FITS o `obs_id`) |
| `timestamp` | `string` | Fecha/hora de captura (ISO o `"n/d"`) |
| `survey_index` | `integer` | Índice del survey espectral asignado al bin |
| `wavelength` | `number` | Longitud de onda teórica del centro del bin espectral (µm) |
| `fits_source` | `string` | URL de acceso al FITS en IRSA (`access_url`, link remoto) |

> **Nota:** Los campos `shape`, `n_invalid_pixels` y el `fits_source` local (ruta del archivo descargado en disco) **no están en esta respuesta rápida**. Se poblan después cuando el background task termina la descarga; consúltalos con `GET /spectral-analyses/{session_id}/observations` una vez que `estado == COMPLETADO`.

### Errores

| Código | Causa | Ejemplo de body |
|--------|-------|-----------------|
| `400` | Campo inválido (fuera de rango, tipo incorrecto) | `{"detail": "..."}` |
| `500` | Error interno consultando IRSA o guardando sesión | `{"detail": "..."}` |

---

## 2. Consultar estado de sesión

**`GET /spectral-analyses/{session_id}`**

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `session_id` | `string` (UUID) | Sí | ID de sesión en la ruta |

### Salida exitosa (`200 OK`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `session_id` | `string` | ID de sesión |
| `estado` | `string` | Estado actual (`"EN_PROCESO"`, `"COMPLETADO"`, `"ERROR"`) |
| `progreso_porcentaje` | `number` | Progreso 0–100 |
| `total_observaciones_grupo` | `integer` | Total de observaciones del grupo |
| `observaciones_descargadas` | `integer` | Cuántas se descargaron |
| `candidatos_detectados` | `integer` | Cuántos candidatos encontró Etner |
| `error_detail` | `string \| null` | Detalle de error si lo hay |

### Errores

| Código | Causa |
|--------|-------|
| `404` | Sesión no encontrada |
| `500` | Error interno del servidor |

---

## 3. Resumen de observaciones (sin matrices)

**`GET /spectral-analyses/{session_id}/observations`**

Devuelve la lista de observaciones de la sesión.

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `session_id` | `string` (UUID) | Sí | ID de sesión en la ruta |

### Salida exitosa (`200 OK`)

Array de objetos con campos:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_exposicion` | `string` | ID de observación |
| `timestamp` | `string` | Fecha/hora de captura |
| `survey_index` | `integer` | Índice del survey |
| `wavelength` | `number \| null` | Longitud de onda en µm |
| `bandwidth` | `number \| null` | Ancho de banda |
| `fits_source` | `string` | Ruta del archivo FITS |
| `shape` | `array[number]` | `[alto, ancho]` |
| `n_invalid_pixels` | `integer \| null` | Pixeles inválidos |

### Errores

| Código | Causa |
|--------|-------|
| `404` | Sesión no encontrada |
| `500` | Error interno |

---

## 4. Lista de imágenes y URLs de descarga

**`GET /spectral-analyses/{session_id}/images`**

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `session_id` | `string` (UUID) | Sí | ID de sesión en la ruta |

### Salida exitosa (`200 OK`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `session_id` | `string` | ID de sesión |
| `total_imagenes` | `integer` | Cantidad de imágenes |
| `imagenes` | `array` | Lista de `ImageListItem` |

Cada `ImageListItem`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `obs_id` | `string` | ID de observación |
| `survey_index` | `integer` | Índice del sondeo (propio de la observación) |
| `wavelength_um` | `number` | Longitud de onda en µm |
| `shape` | `array[number]` | `[alto, ancho]` |
| `preview_png_url` | `string` | Ruta relativa para ver el PNG |
| `fits_download_url` | `string` | Ruta relativa para descargar el FITS |

### Errores

| Código | Causa |
|--------|-------|
| `404` | Sesión no encontrada |
| `500` | Error interno |

---

## 5. Previsualización PNG

**`GET /spectral-analyses/{session_id}/images/{obs_id}/preview.png`**

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `session_id` | `string` (UUID) | Sí | ID de sesión |
| `obs_id` | `string` | Sí | ID de observación |

### Salida exitosa (`200 OK`)

- `Content-Type: image/png`
- Cuerpo: bytes de la imagen

### Errores

| Código | Causa |
|--------|-------|
| `404` | Preview no encontrada o sesión inexistente |

---

## 6. Descarga del FITS original

**`GET /spectral-analyses/{session_id}/images/{obs_id}/file.fits`**

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `session_id` | `string` (UUID) | Sí | ID de sesión |
| `obs_id` | `string` | Sí | ID de observación |

### Salida exitosa (`200 OK`)

- `Content-Type: application/fits`
- `Content-Disposition: attachment; filename="{obs_id}.fits"`
- Cuerpo: bytes del archivo FITS

### Errores

| Código | Causa |
|--------|-------|
| `404` | FITS no encontrado o sesión inexistente |

---

## 7. Composición falso color RGB por survey

**`POST /spectral-analyses/rgb-composite`**

Genera una composición RGB falsa **por survey (época)**: una imagen por survey común a los tres canales. Para cada canal consulta Elide con el detector `SPHEREx-D{sensor}` y el grupo espectral pedido, agrupa las observaciones en surveys (gaps temporales > 45 días) y arma un PNG RGB por survey común. Cada PNG se persiste en el volumen de imágenes y se sirve mediante el endpoint GET de descarga.

### Entrada

Cuerpo:

| Campo | Tipo | Requerido | Descripción | Ejemplo |
|-------|------|-----------|-------------|---------|
| `ra` | `number` | Sí | Ascensión recta en grados (0–360) | `210.80227` |
| `dec` | `number` | Sí | Declinación en grados (-90–90) | `54.34895` |
| `size_deg` | `number` | No | Tamaño del lado del recorte en grados (>0, default 0.85) | `0.85` |
| `channels` | `array` | Sí | Definición de canales RGB (1 a 3) | ver abajo |

Cada ítem de `channels`:

| Campo | Tipo | Requerido | Descripción | Ejemplo |
|-------|------|-----------|-------------|---------|
| `channel` | `string` | Sí | Color: `"red"`, `"green"` o `"blue"` | `"red"` |
| `sensor` | `integer` | Sí | Número de detector SPHEREx (1–6) | `2` |
| `group` | `integer` | Sí | Grupo espectral (1–17) | `5` |

### Salida exitosa (`200 OK`)

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

### Errores

| Código | Causa | Ejemplo de body |
|--------|-------|-----------------|
| `400` | Error de validación (canal faltante, sin observaciones para un canal) | `{"detail": "..."}` |

---

## 8. Descarga de composición RGB (PNG)

**`GET /spectral-analyses/rgb-composites/{composite_id}.png`**

Devuelve el archivo PNG de una composición RGB generada por `POST /rgb-composite`.

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `composite_id` | `string` | Sí | Identificador de la composición (viene en `composites[].composite_id`) |

### Salida exitosa (`200 OK`)

- `Content-Type: image/png`
- `Cache-Control: public, max-age=86400, immutable`
- Cuerpo: bytes de la imagen compuesta

### Errores

| Código | Causa |
|--------|-------|
| `404` | Composite PNG no existe |

---

## 8. Candidatos de movimiento (Etner)

**`GET /spectral-analyses/{session_id}/candidates`**

Solo disponible cuando `estado == COMPLETADO`.

Devuelve candidatos organizados por pares de surveys consecutivos ejecutados en paralelo.

### Entrada

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `session_id` | `string` (UUID) | Sí | ID de sesión |

### Salida exitosa (`200 OK`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `session_id` | `string` | ID de sesión |
| `total_candidatos` | `integer` | Total de candidatos en todos los pares |
| `pairs` | `array` | Lista de pares de surveys |

Cada `pair`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `survey_pair` | `array[integer]` | Par de surveys analizados, ej. `[1, 2]` |
| `total_candidatos` | `integer` | Candidatos en este par |
| `candidatos` | `array` | Lista de candidatos |

Cada candidato:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `candidate_id` | `string` | Identificador del candidato |
| `ra` | `number` | Ascensión recta |
| `dec` | `number` | Declinación |
| `snr` | `number` | Signal-to-noise ratio |
| `motion_arcsec_yr` | `number` | Movimiento en arcsegundos por año |
| `status` | `string` | Estado del candidato (ej. `"VALIDATED"`) |

Ejemplo con 3 surveys (2 pares):

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

### Errores

| Código | Causa |
|--------|-------|
| `400` | Estado no es `COMPLETADO` |
| `404` | Sesión no encontrada |
| `500` | Error interno |

---

## 9. Health check

**`GET /health`** (sin prefijo `/api/v1`)

### Salida exitosa (`200 OK`)

```json
{
  "status": "ok",
  "storage_type": "memory"
}
```

### Errores

| Código | Causa |
|--------|-------|
| `500` | Error interno del servidor |

---

## Notas generales para el front

- Guarda el `session_id` del `POST /spectral-analyses`; lo necesitas en todas las llamadas siguientes.
- El procesamiento es asíncrono: tras iniciar, `estado` empieza como `"EN_PROCESO"` y pasa a `"COMPLETADO"` cuando termina la Fase 2.
- Los candidatos de movimiento (`/candidates`) solo están disponibles cuando `estado == COMPLETADO`.
- Los candidatos se analizan por pares de surveys consecutivos en paralelo: 3 surveys generan pares (1,2) y (2,3); 4 surveys generan (1,2), (2,3) y (3,4).
- El endpoint `rgb-composite` está en proceso.
- `/v1/models` **no es un endpoint de esta API**. Si algún cliente lo consulta, recibirá `404 Not Found`.
