# PROGRAMADOR 4 — Frontend / Visualization

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
