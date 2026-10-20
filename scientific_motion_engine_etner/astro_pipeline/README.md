# 🌌 SPHEREx Scientific Motion Engine (`astro_pipeline`)

> **NASA Space Apps Challenge 2026** — *Detección de Objetos en Movimiento y Búsqueda del Planeta X / TNOs con Datos Espectrofotométricos de SPHEREx*  
> **Módulo:** `scientific_motion_engine_etner/astro_pipeline`  
> **Responsable / Programador Científico:** Etner  
> **Archivo Principal:** [`main.py`](file:///z:/PROYECTOS%20PERSONALES/NASA%20ESPACE%20APPS%20CHALLENGE%202026/nasa-space-challenge-planeta-x-spherex/scientific_motion_engine_etner/astro_pipeline/main.py)

---

## 📋 Tabla de Contenidos

1. [Visión General del Módulo](#1-visión-general-del-módulo)
2. [Arquitectura y Flujo de Procesamiento](#2-arquitectura-y-flujo-de-procesamiento)
3. [Explicación Detallada Módulo por Módulo](#3-explicación-detallada-módulo-por-módulo)
   - [Módulo 1: Contratos de Datos y Tipado Estricto](#módulo-1-contratos-de-datos-y-tipado-estricto)
   - [Módulo 2: Lector Resiliente de FITS SPHEREx (`load_spherex_observation`)](#módulo-2-lector-resiliente-de-fits-spherex-load_spherex_observation)
   - [Módulo 3: Utilidades Científicas y Preprocesamiento](#módulo-3-utilidades-científicas-y-preprocesamiento)
   - [Módulo 4: Núcleo de Detección Temporal (`analyze_observations`)](#módulo-4-núcleo-de-detección-temporal-analyze_observations)
   - [Módulo 5: Generador de FITS Sintéticos (`create_mock_spherex_fits`)](#módulo-5-generador-de-fits-sintéticos-create_mock_spherex_fits)
   - [Módulo 6: Motor de Visualización Astronómica (`visualize_candidates_on_image`)](#módulo-6-motor-de-visualización-astronómica-visualize_candidates_on_image)
   - [Módulo 7: Punto de Entrada y Ejecución Batch (`if __name__ == '__main__'`)](#módulo-7-punto-de-entrada-y-ejecución-batch-if-__name__--__main__)
4. [Fundamento Físico y Matemático](#4-fundamento-físico-y-matemático)
5. [Contrato de Datos Entrada / Salida (API JSON)](#5-contrato-de-datos-entrada--salida-api-json)
6. [Instalación y Requisitos](#6-instalación-y-requisitos)
7. [Guía de Ejecución](#7-guía-de-ejecución)

---

## 1. Visión General del Módulo

El **Scientific Motion Engine** es el componente algorítmico y matemático central del proyecto. Su función primordial es recibir observaciones astronómicas en formato FITS del telescopio espacial **SPHEREx** (*Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer*) tomadas en diferentes momentos del tiempo (épocas), alinearlas espacialmente mediante WCS (*World Coordinate System*), sustraer el fondo cósmico y de luz zodiacal, y aislar fuentes transitorias o con **movimiento propio aparente** (como asteroides, cometas, Objetos Transneptunianos —TNOs— y el hipotético **Planeta Nueve / Planeta X**).

### Objetivos Clave
- Procesar imágenes espectroscópicas infrarrojas calibradas de SPHEREx (Nivel 2).
- Realizar sustracción temporal (*Image Differencing*) ponderada por matrices de varianza reales ($\sigma^2$).
- Detectar fuentes de señal transitoria evitando falsos positivos producidos por desalineaciones de estrellas fijas o píxeles defectuosos.
- Entregar coordenadas celestes exactas (RA, Dec en J2000), velocidad angular aparente ($''/\text{año}$) y significancia estadística ($SNR$).
- Generar visualizaciones diagnósticas de alta fidelidad astronómica con estiramiento hiperbólico (*asinh stretch*) y paneles de zoom (*cutouts*).

---

## 2. Arquitectura y Flujo de Procesamiento

El pipeline opera de forma lineal, determinista y modular:

```mermaid
flowchart TD
    A["Archivos FITS SPHEREx (Level 2)"] --> B["load_spherex_observation()"]
    B -->|Extracción IMAGE, VARIANCE, FLAGS, ZODI, WCS, Epoch| C["Contrato Observation"]
    C --> D["preprocess_and_normalize()"]
    D -->|Enmascaramiento de bad pixels & sustracción de fondo robusto| E["align_observation() via reproject_interp"]
    E -->|Cuadrícula común en WCS de referencia| F["analyze_observations()"]
    F -->|Image Differencing & Propagación de Varianza| G["Mapa de SNR = ΔI / √(σ₁² + σ₂²)"]
    G --> H["detect_snr_peaks() (Picos Positivos & Negativos)"]
    H --> I["Emparejamiento 1-a-1 & Veto Anti-Estrellas Fijas"]
    I --> J["Cálculo Astrométrico: RA, Dec, Desplazamiento (\") y Velocidad (\"/año)"]
    J --> K["AnalysisResult (Candidatos en JSON)"]
    K --> L["visualize_candidates_on_image()"]
    L --> M["PNG Diagnóstico con Cutouts & Coordenadas WCS"]
```

---

## 3. Explicación Detallada Módulo por Módulo

A continuación se detalla la función, lógica interna, parámetros y decisiones de diseño de cada una de las secciones de [`main.py`](file:///z:/PROYECTOS%20PERSONALES/NASA%20ESPACE%20APPS%20CHALLENGE%202026/nasa-space-challenge-planeta-x-spherex/scientific_motion_engine_etner/astro_pipeline/main.py):

---

### Módulo 1: Contratos de Datos y Tipado Estricto
*(Líneas 32 a 62)*

Define las estructuras de datos que garantizan la interoperabilidad limpia con el pipeline de descarga de datos (Elide), la API de Backend (Anghelo) y el Frontend (Andy).

| Clase | Atributos | Propósito |
| :--- | :--- | :--- |
| [`Observation`](file:///z:/PROYECTOS%20PERSONALES/NASA%20ESPACE%20APPS%20CHALLENGE%202026/nasa-space-challenge-planeta-x-spherex/scientific_motion_engine_etner/astro_pipeline/main.py#L35-L42) | `data` (`np.ndarray` 2D)<br>`variance` (`np.ndarray` 2D)<br>`mask` (`np.ndarray` booleana)<br>`wcs` (`WCS` de Astropy)<br>`epoch` (`Time` de Astropy) | Representa una toma astronómica completa en unidades de $MJy/sr$, con su mapa de incertidumbre formal ($\sigma^2$), máscara de píxeles corruptos, solución astrométrica WCS y fecha/hora precisa. |
| [`Candidate`](file:///z:/PROYECTOS%20PERSONALES/NASA%20ESPACE%20APPS%20CHALLENGE%202026/nasa-space-challenge-planeta-x-spherex/scientific_motion_engine_etner/astro_pipeline/main.py#L44-L52) | `id` (`str`)<br>`ra` (`float` en grados J2000)<br>`dec` (`float` en grados J2000)<br>`displacementArcsec` (`float`)<br>`motionArcsecPerYear` (`float`)<br>`snr` (`float`) | Información cinemática y astrométrica de una fuente detectada en movimiento. |
| [`AnalysisResult`](file:///z:/PROYECTOS%20PERSONALES/NASA%20ESPACE%20APPS%20CHALLENGE%202026/nasa-space-challenge-planeta-x-spherex/scientific_motion_engine_etner/astro_pipeline/main.py#L55-L61) | `candidates` (`List[Candidate]`) | Contenedor principal que expone el método `.to_dict()`, permitiendo serialización instantánea a JSON estándar. |

---

### Módulo 2: Lector Resiliente de FITS SPHEREx (`load_spherex_observation`)
*(Líneas 67 a 170)*

Esta función lee archivos FITS Level 2 generados por el telescopio espacial SPHEREx o descargados desde NASA IPAC/IRSA.

#### Características críticas implementadas:
1. **Resiliencia ante descargas incompletas (`ignore_missing_end=True`):** Si un archivo FITS se interrumpió en red o disco antes del bloque final `END`, la función recupera los datos válidos sin fallar catastróficamente.
2. **Inspección Dinámica de HDUs:** Localiza automáticamente la extensión científica buscando iterativamente por nombres estándar (`'IMAGE'`, `'SCI'`, `'PRIMARY'`) o cualquier HDU con matriz 2D.
3. **Detección de Truncamiento en Disco:** Los archivos FITS incompletos rellenan los sectores finales del arreglo con ceros binarios exactos (`0.0`). La función crea una máscara `truncated_mask` para identificarlos y aislarlos, previniendo falsos gradientes.
4. **Sustracción de Luz Zodiacal (`ZODI`):** SPHEREx opera en el infrarrojo cercano ($0.75 - 5.0\,\mu m$), donde la luz zodiacal (dispersión solar por polvo interplanetario) domina el fondo del cielo. Si la extensión `ZODI` está presente, se resta directamente de la señal científica:
   $$\text{data}_{\text{clean}} = \text{data}_{\text{raw}} - \text{ZODI}$$
5. **Manejo Riguroso de Varianza e Incertidumbre:** Busca extensiones `'VARIANCE'`, `'VAR'`, `'UNCERTAINTY'` o `'ERR'`. Si el archivo contiene error estándar ($\sigma$), lo eleva automáticamente al cuadrado para obtener varianza ($\sigma^2$).
6. **Fallback de Varianza mediante MAD:** Si el FITS carece de extensión de varianza, calcula la varianza del fondo usando la desviación absoluta mediana (*Median Absolute Deviation* - MAD), inmune a fuentes puntuales brillantes:
   $$\sigma_{\text{est}} = 1.4826 \times \text{mediana}(|x - \text{mediana}(x)|) \implies \text{Var} = \sigma_{\text{est}}^2$$
7. **Filtrado Bit a Bit de Calidad (`FLAGS` / `DQ`):** Evalúa máscaras de banderas de calidad mediante operaciones a nivel de bits con `bitmask_ignore`.
8. **Detección Multiformato de Épocas:** Lee y parsea fechas en múltiples formatos astronómicos estándar (`MJD-AVG`, `MJD-OBS`, `MJD`, `DATE-AVG`, `DATE-OBS`, `DATE`).

---

### Módulo 3: Utilidades Científicas y Preprocesamiento
*(Líneas 175 a 267)*

#### 1. `smooth_gaussian_np(img, sigma=0.8)`
Aplica un filtro gaussiano bidimensional separable implementado en NumPy puro (sin depender de bibliotecas externas pesadas). Convoluciona primero a lo largo de las filas y luego de las columnas con un kernel gaussiano truncado a $3\sigma$, optimizando el rendimiento.

#### 2. `preprocess_and_normalize(obs: Observation)`
- Sustituye píxeles marcados como corruptos en la máscara por valores `NaN`.
- Estima el fondo local del cielo mediante la mediana robusta (`nanmedian`).
- Estandariza la dispersión de los datos mediante el MAD escalado ($1.4826 \times \text{MAD}$).
- Retorna la imagen y la varianza escaladas uniformemente, asegurando que tomas de diferentes detectores o épocas tengan el mismo nivel de referencia fotométrico.

#### 3. `align_observation(data, var, wcs_in, wcs_ref, shape_ref)`
- Utiliza la biblioteca especializada `reproject.reproject_interp` para proyectar el flujo de la imagen y su varianza asociada sobre la misma cuadrícula de píxeles y orientación celeste del WCS de referencia.
- Incluye una optimización de cortocircuito: si el encabezado WCS y las dimensiones ya son idénticos, evita el cómputo de reproyección.
- Enmascara los bordes donde el área proyectada (*footprint*) no tiene cobertura completa ($< 0.99$).

#### 4. `detect_snr_peaks(snr_image, valid_mask, threshold=6.0)`
Identifica fuentes puntuales estadísticamente significativas:
- **Margen de seguridad:** Descarta píxeles a menos de 6 píxeles del borde del detector.
- **Pureza de vecindad $5\times 5$:** Exige que toda la vecindad de $5\times 5$ píxeles contenga píxeles válidos (evita que gradientes abruptos en los bordes de la máscara se confundan con estrellas).
- **Condición de máximo local:** El píxel central debe ser el valor más alto en su ventana de $5\times 5$.
- **Centroide Sub-píxel:** Determina el centroide de la fuente con precisión fraccionaria mediante el momento ponderado de intensidad en una ventana $3\times 3$:
  $$x_{\text{cen}} = \frac{\sum x \cdot I(x,y)}{\sum I(x,y)}, \quad y_{\text{cen}} = \frac{\sum y \cdot I(x,y)}{\sum I(x,y)}$$

---

### Módulo 4: Núcleo de Detección Temporal (`analyze_observations`)
*(Líneas 272 a 397)*

Este es el núcleo de cálculo que implementa la detección de objetos móviles entre épocas:

1. **Ordenación Cronológica:** Ordena las observaciones según su día juliano (`epoch.jd`). Si dos tomas comparten la misma estampa temporal por omisión de metadatos, introduce un delta por defecto representativo del barrido semestral de SPHEREx ($182.625$ días).
2. **Alineación al Marco de Referencia:** Adopta la primera época ($t_1$) como marco de coordenadas maestro y alinea las subsecuentes ($t_2$).
3. **Diferenciación Ponderada de Imágenes (*Variance-Weighted Differencing*):**
   Calcula la diferencia de flujo y propaga la varianza cuadrática:
   $$\Delta I = I_{t_2} - I_{t_1}$$
   $$\sigma_{\Delta}^2 = \sigma_1^2 + \sigma_2^2 \implies \text{Ruido} = \sqrt{\sigma_{\Delta}^2}$$
   $$SNR(x,y) = \frac{\Delta I(x,y)}{\text{Ruido}(x,y)}$$
4. **Física del Dipolo de Movimiento:**
   Cuando un objeto celeste se mueve entre $t_1$ y $t_2$:
   - En $t_2$ aparece un **pico positivo** en el mapa de diferencia ($SNR > 0$).
   - En $t_1$ queda un **pozo negativo** o vacío en el mapa de diferencia (detectado buscando en $-SNR$).
5. **Algoritmo de Emparejamiento 1-a-1:**
   - Calcula la distancia euclidiana entre cada par de picos positivo/negativo y su relación de flujo:
     $$\text{distancia} = \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}, \quad \text{ratio} = \frac{SNR_{\text{pos}}}{SNR_{\text{neg}}}$$
   - **Rango de Distancia Admisible:** $1.3 \le \text{dist} \le 8.0$ píxeles. El límite inferior de $1.3$ píxeles es un filtro astronómico crucial que descarta residuos de dipolos microscópicos originados por la resta imperfecta de estrellas estáticas brillantes. El límite superior de 8 píxeles corresponde a $\sim 49''$ en la escala de SPHEREx.
   - **Consistencia de Flujo:** Exige que $0.6 \le \text{ratio} \le 1.67$, garantizando que la fuente conserve aproximadamente su luminosidad intrínseca entre ambas observaciones.
   - **Asignación Exclusiva Voraz (Greedy 1-a-1):** Ordena los candidatos de menor a mayor separación para garantizar que ningún pico positivo o negativo sea asignado a más de un objeto.
6. **Veto Anti-Estrellas Fijas:**
   Verifica que en la imagen $I_{t_2}$ la posición original $(x_1, y_1)$ esté a nivel de fondo cósmico, y que en $I_{t_1}$ la nueva posición $(x_2, y_2)$ haya estado vacía. Si alguna posición supera $4\sigma$ de brillo residual, se rechaza de inmediato (estrella de fondo estática).
7. **Cinemática y Astrometría:**
   - Convierte los centroides sub-píxel a coordenadas celestes mundiales:
     $$\text{coord}_1 = WCS(x_1, y_1), \quad \text{coord}_2 = WCS(x_2, y_2)$$
   - Calcula la separación angular real en la esfera celeste mediante trigonometría esférica:
     $$\Delta\theta = \text{separation}(\text{coord}_1, \text{coord}_2) \quad [\text{arcsec}]$$
   - Deriva el movimiento propio aparente anualizado:
     $$\mu = \frac{\Delta\theta}{\Delta t_{\text{años}}} \quad [{}''/\text{año}]$$

---

### Módulo 5: Generador de FITS Sintéticos (`create_mock_spherex_fits`)
*(Líneas 402 a 455)*

Permite ejecutar pruebas unitarias, de integración y validación algorítmica sin necesidad de descargar gigabytes de datos de misiones reales:
- Configura una escala de placa idéntica a SPHEREx: **$6.15''/\text{píxel}$** con proyección tangencial (`RA---TAN`, `DEC--TAN`).
- Añade emisión zodiacal difusa uniforme ($50\,MJy/sr$).
- Inyecta ruido gaussiano con varianza realista ($\sigma = 2.0$).
- Introduce estrellas fijas estáticas con PSF gaussiana.
- Simula un objeto en movimiento translacional con desplazamiento configurable entre épocas.
- Inyecta píxeles anómalos (*cosmic rays* / *hot pixels*, ej. valor `99999.0` con bandera en `FLAGS`) para validar que las máscaras descarten artefactos eficazmente.

---

### Módulo 6: Motor de Visualización Astronómica (`visualize_candidates_on_image`)
*(Líneas 460 a 715)*

Produce visualizaciones con estética profesional e informativa, aptas para presentaciones a jurados y paneles de control:

1. **Estiramiento Asinh (`_asinh_stretch`):**
   Aplica la función arco seno hiperbólico ($asinh$) con percentiles de rechazo ($q = 0.005$):
   $$I_{\text{display}} = \frac{\text{asinh}(I_{\text{norm}} / a)}{\text{asinh}(1 / a)}$$
   Esto permite visualizar simultáneamente fuentes muy débiles y estrellas brillantes sin saturación ni amplificación excesiva del ruido de fondo.
2. **Colormap Infrarrojo Personalizado (`spherex_infrared`):**
   Paleta de colores astronómica diseñada a medida: parte de negro espacial profundo (`#050510`), pasando por azul noche, magenta cósmico, rojo-naranja y amarillo solar hasta blanco brillante.
3. **Composición Gráfica con `GridSpec`:**
   - **Panel Principal (75% del ancho):** Vista completa del campo del cielo proyectada en coordenadas astrométricas reales con ejes en Ascensión Recta y Declinación (J2000). Cada candidato se destaca con un marco redondeado (`FancyBboxPatch`), cruceta sub-píxel y etiqueta translúcida.
   - **Caja de Metadatos:** Indica el total de candidatos hallados, la época de la toma y la resolución del campo en píxeles.
   - **Mosaico Lateral de Cutouts (25% del ancho):** Hasta 6 paneles individuales ampliados con zoom sobre cada candidato detectado, mostrando su ID, SNR, desplazamiento angular ($\Delta$) y velocidad aparente ($\mu$ en $''/\text{año}$).
   - **Barra de Escala Fotométrica y Sello:** Barra horizontal con gradiente de intensidad y pie de autoría del proyecto.

---

### Módulo 7: Punto de Entrada y Ejecución Batch (`if __name__ == '__main__'`)
*(Líneas 718 a 757)*

- Localiza automáticamente el directorio de datos `spherex_6_bandas` adyacente a la carpeta del pipeline.
- Descubre y ordena los archivos FITS de nivel 2 disponibles (`level2_*`).
- Instancia las observaciones llamando a `load_spherex_observation`.
- Ejecuta `analyze_observations()` sobre pares de épocas consecutivas.
- Imprime la salida JSON estructurada en consola.
- Genera y guarda automáticamente la imagen de diagnóstico [`candidates_marked.png`](file:///z:/PROYECTOS%20PERSONALES/NASA%20ESPACE%20APPS%20CHALLENGE%202026/nasa-space-challenge-planeta-x-spherex/scientific_motion_engine_etner/astro_pipeline/candidates_marked.png).

---

## 4. Fundamento Físico y Matemático

### 1. Escala Espacial y Temporal de SPHEREx
- **Tamaño de Píxel:** $6.15''$ por píxel.
- **Cadencia de Sondeo:** El telescopio escanea el cielo completo cada 6 meses ($\Delta t \approx 0.5\,\text{años}$).
- **Umbral de Movimiento:** Para objetos del cinturón de Kuiper y Planeta X, el movimiento propio aparente proyectado por paralaje orbital heliocéntrica varía típicamente entre $2''/\text{año}$ y $60''/\text{año}$. Una traslación de $1.3$ a $8$ píxeles en 6 meses cubre perfectamente este rango astronómico ($16''/\text{año} \le \mu \le 98''/\text{año}$).

### 2. Formulación de Relación Señal-Ruido (SNR)
Para dos épocas independientes con errores no correlacionados, la varianza de la diferencia es la suma de las varianzas individuales:
$$\sigma_{\text{diff}}^2(x, y) = \sigma_{1}^2(x, y) + \sigma_{2}^2(x, y)$$
$$SNR(x, y) = \frac{I_2(x, y) - I_1(x, y)}{\sqrt{\sigma_1^2(x, y) + \sigma_2^2(x, y)}}$$
El umbral por defecto $\text{SNR} \ge 6.0$ corresponde a una probabilidad de falsa alarma por fluctuación gaussiana puramente estadística inferior a $10^{-9}$ por píxel.

---

## 5. Contrato de Datos Entrada / Salida (API JSON)

### Salida JSON de `analyze_observations(...)`:

```json
{
  "candidates": [
    {
      "id": "C-001",
      "ra": 149.991205,
      "dec": 1.998412,
      "displacementArcsec": 18.4521,
      "motionArcsecPerYear": 36.9042,
      "snr": 14.85
    },
    {
      "id": "C-002",
      "ra": 150.012540,
      "dec": 2.015630,
      "displacementArcsec": 12.3015,
      "motionArcsecPerYear": 24.6030,
      "snr": 9.21
    }
  ]
}
```

---

## 6. Instalación y Requisitos

### Requisitos de Sistema
- Python **3.10** o superior.
- Espacio en disco suficiente para los archivos FITS de SPHEREx (desde unos pocos megabytes en cutouts hasta $\sim 70\,\text{MB}$ por archivo Level 2 completo).

### Dependencias Principales

```bash
pip install numpy astropy reproject matplotlib
```

*(Opcional: Si se desea acelerar reproyecciones masivas, se puede instalar `scipy`)*.

---

## 7. Guía de Ejecución

### Ejecución Directa del Pipeline
Desde la terminal en el entorno virtual del proyecto:

```powershell
cd "z:\PROYECTOS PERSONALES\NASA ESPACE APPS CHALLENGE 2026\nasa-space-challenge-planeta-x-spherex\scientific_motion_engine_etner\astro_pipeline"
python main.py
```

### Uso Programático desde Otros Módulos (Backend / API)

```python
from scientific_motion_engine_etner.astro_pipeline.main import (
    load_spherex_observation,
    analyze_observations,
    visualize_candidates_on_image
)

# 1. Cargar observaciones de distintas épocas
obs1 = load_spherex_observation("ruta/a/epoca1.fits")
obs2 = load_spherex_observation("ruta/a/epoca2.fits")

# 2. Ejecutar el motor de detección de movimiento
resultado = analyze_observations([obs1, obs2], snr_threshold=6.0)

# 3. Inspeccionar candidatos
for cand in resultado["candidates"]:
    print(f"[{cand['id']}] RA: {cand['ra']}° | Dec: {cand['dec']}° | Mov: {cand['motionArcsecPerYear']}\"/yr | SNR: {cand['snr']}")

# 4. Generar la imagen visual de diagnóstico
if resultado["candidates"]:
    visualize_candidates_on_image(
        observation=obs1,
        candidates=resultado["candidates"],
        output_path="salida_candidatos.png",
        show_plot=False
    )
```

---

## 👥 Integración en el Equipo del Proyecto

- **Entrada:** Recibe los datos y cutouts FITS organizados por **Elide** (`spherex_data_pipeline_elide`).
- **Salida:** Entrega la estructura `AnalysisResult` en JSON a **Anghelo** (`backend_api_integration_anghelo`) para alimentar los endpoints REST/FastAPI.
- **Visualización:** Genera las imágenes diagnósticas e información de cutouts consumida por la interfaz de usuario desarrollada por **Andy** (`frontend_visualization_andy`).
