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
