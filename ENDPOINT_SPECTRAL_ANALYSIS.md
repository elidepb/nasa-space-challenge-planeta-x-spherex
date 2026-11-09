# Endpoint espectral — referencia rápida

La documentación canónica está en:

[`backend_api_integration_anghelo/README.md`](backend_api_integration_anghelo/README.md)

Swagger: `http://localhost:8000/docs`

## Resumen para el frontend

| Método | Ruta | Notas |
| --- | --- | --- |
| `POST` | `/api/v1/spectral-analyses` | Body `{ ra, dec, size_deg, bandpass?, spectral_group? }` → **202** |
| `GET` | `/api/v1/spectral-analyses/{session_id}` | `estado`, `progreso_porcentaje`, … |
| `GET` | `…/observations` | Resumen sin matrices |
| `GET` | `…/images` | `preview_png_url` + `fits_download_url` |
| `GET` | `…/images/{obs_id}/preview.png` | PNG |
| `GET` | `…/candidates` | Solo si `estado == COMPLETADO` |
| `GET` | `/health` | Sin prefijo `/api/v1` |

Adaptador del front: `frontend_visualization_andy/src/api/spectralAnalysis.ts` + `httpApi.ts`.

Modo HTTP:

```env
VITE_API_MODE=http
VITE_API_URL=http://localhost:8000
```
