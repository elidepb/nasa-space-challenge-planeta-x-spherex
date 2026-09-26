# NASA SPACE CHALLENGE — Planeta X y SPHEREx

## TARJETA GENERAL — PROYECTO SPHEREx

**Objetivo**

Desarrollar una aplicación web que permita seleccionar una región del cielo observada por SPHEREx, recuperar observaciones FITS de diferentes épocas, procesarlas y compararlas para visualizar cambios y detectar posibles objetos en movimiento.

**Flujo general**

1. Seleccionar una región mediante coordenadas RA/Dec.
2. Consultar observaciones SPHEREx disponibles para esa región.
3. Descargar o solicitar cutouts FITS de diferentes épocas.
4. Extraer y preparar los datos científicos de los FITS.
5. Alinear observaciones de la misma región.
6. Comparar imágenes entre épocas.
7. Detectar fuentes que cambien de posición.
8. Calcular posición, desplazamiento y métricas básicas de los candidatos.
9. Exponer resultados mediante API.
10. Visualizar observaciones, diferencias y candidatos en una interfaz web.

**Contrato principal de datos**

`Observation`
- id
- timestamp
- ra
- dec
- detector
- wavelength
- image/cutout
- FITS source
- metadata

`Candidate`
- id
- ra
- dec
- detections por época
- displacementArcsec
- motionArcsecPerYear
- snr
- status

**Entregable final**

Aplicación funcional donde el usuario pueda:
- introducir o seleccionar una región del cielo;
- consultar observaciones disponibles;
- visualizar diferentes épocas;
- usar comparación temporal/blink;
- visualizar imagen de diferencias;
- ver candidatos detectados;
- inspeccionar posición y desplazamiento de cada candidato.

---

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

---

# Etner — Scientific / Motion Engine

**Programador:** Etner

**Responsabilidad**

Procesar las observaciones y detectar cambios o movimiento entre épocas.

**Tareas**

1. Recibir una lista de `Observation`.
2. Leer las matrices científicas preparadas.
3. Aplicar máscaras de calidad.
4. Alinear las observaciones usando WCS.
5. Reproyectar imágenes a una cuadrícula común cuando sea necesario.
6. Normalizar fondo e intensidad entre épocas.
7. Comparar imágenes correspondientes a tiempos diferentes.
8. Implementar image differencing.
9. Utilizar VARIANCE para estimar significancia/SNR.
10. Detectar fuentes o regiones significativas en las imágenes de diferencia.
11. Relacionar detecciones entre diferentes épocas.
12. Calcular:
    - RA;
    - Dec;
    - desplazamiento angular;
    - intervalo temporal;
    - movimiento angular por unidad de tiempo;
    - SNR.
13. Filtrar detecciones inconsistentes o artefactos básicos.
14. Generar una lista de candidatos usando el contrato `Candidate`.

**Interfaz esperada**

```python
analyze_observations(
    observations
) -> AnalysisResult
```

**Salida mínima**

```json
{
  "candidates": [
    {
      "id": "C-001",
      "ra": 0,
      "dec": 0,
      "displacementArcsec": 0,
      "motionArcsecPerYear": 0,
      "snr": 0
    }
  ]
}
```

**Tecnologías**

- Python
- NumPy
- Astropy
- Photutils
- Reproject
- SciPy cuando sea necesario

**Entregables**

- pipeline de comparación temporal;
- alineación de observaciones;
- difference images;
- detección de candidatos;
- cálculo de desplazamiento;
- resultados compatibles con `Candidate`.

---

# Anghelo — Backend / API / Integration

**Programador:** Anghelo

**Responsabilidad**

Construir la capa que conecta datos, procesamiento científico y frontend.

**Tareas**

1. Crear backend con FastAPI.
2. Definir modelos `Observation`, `Candidate` y `AnalysisResult`.
3. Crear inicialmente mocks para que el frontend pueda trabajar sin depender del pipeline real.
4. Implementar endpoints para:
   - solicitar análisis de una región;
   - consultar observaciones;
   - consultar resultados;
   - consultar candidatos;
   - recuperar imágenes procesadas.
5. Integrar posteriormente el módulo del Programador 1.
6. Integrar el motor científico del Programador 2.
7. Gestionar estados de ejecución:
   - pendiente;
   - procesando;
   - completado;
   - error.
8. Gestionar almacenamiento temporal de:
   - FITS;
   - cutouts;
   - imágenes procesadas;
   - difference images;
   - resultados.
9. Implementar manejo de errores.
10. Implementar caché básica para evitar descargar o procesar repetidamente la misma región.
11. Preparar configuración de desarrollo y producción.
12. Publicar documentación básica de endpoints.

**Endpoints mínimos**

```text
POST /analysis

GET /analysis/{id}

GET /analysis/{id}/observations

GET /analysis/{id}/candidates

GET /analysis/{id}/images
```

**Entregables**

- API funcional;
- schemas compartidos;
- endpoints documentados;
- mocks iniciales;
- integración con P1 y P2;
- backend desplegable.

---

# Andy — Frontend / Visualization

**Programador:** Andy

**Responsabilidad**

Construir la interfaz para explorar observaciones SPHEREx y resultados del análisis.

**Tareas**

1. Crear interfaz web principal.
2. Permitir ingresar o seleccionar:
   - RA;
   - Dec;
   - tamaño de región.
3. Consumir inicialmente datos mock.
4. Consumir posteriormente la API real.
5. Crear visor de la región observada.
6. Mostrar las observaciones disponibles ordenadas temporalmente.
7. Implementar:
   - cambio manual entre épocas;
   - timeline;
   - Play/Pause;
   - Blink Mode;
   - Difference Mode.
8. Implementar zoom y desplazamiento del visor.
9. Mostrar fecha, detector y longitud de onda de la observación activa.
10. Dibujar candidatos sobre las imágenes.
11. Permitir seleccionar un candidato.
12. Mostrar para cada candidato:
    - RA;
    - Dec;
    - desplazamiento;
    - movimiento;
    - SNR;
    - observaciones asociadas.
13. Mostrar visualmente la trayectoria del candidato entre épocas.
14. Manejar estados:
    - sin resultados;
    - cargando;
    - procesando;
    - error;
    - análisis completado.
15. Adaptar la interfaz a desktop para la demostración.

**Pantalla principal mínima**

```text
RA / DEC / Search

        SKY VIEW

Epoch: [----------------●------]

Previous | Play | Next
Blink | Difference | Original

Candidates
- C-001
- C-002

Candidate details
RA
DEC
Motion
SNR
```

**Entregables**

- frontend funcional;
- visor de observaciones;
- timeline;
- blink mode;
- difference mode;
- overlays de candidatos;
- integración final con API.
