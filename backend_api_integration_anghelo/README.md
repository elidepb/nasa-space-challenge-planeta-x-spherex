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
