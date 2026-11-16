# NASA SPACE APPS CHALLENGE 2026 — Planet X & SPHEREx

[![NASA Space Apps Challenge](https://img.shields.io/badge/NASA%20Space%20Apps-Challenge%202026-blue.svg)](https://www.spaceappschallenge.org/)
[![Mission](https://img.shields.io/badge/NASA-SPHEREx-orange.svg)](https://spherex.caltech.edu/)
[![Data Source](https://img.shields.io/badge/Data-NASA%2FIPAC%20IRSA-green.svg)](https://irsa.ipac.caltech.edu/)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF.svg)](https://vitejs.dev/)

An open-source, scientific web platform designed to explore, temporally compare, and detect apparent moving objects (asteroids, comets, brown dwarfs, Trans-Neptunian Objects —TNOs— and the hypothetical **Planet Nine / Planet X**) using near-infrared spectrophotometric data from NASA's **SPHEREx** space observatory (*Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer*).

---

## 👥 Project Team

| Member | Role | Primary Folder / Component | Key Responsibility |
| :--- | :--- | :--- | :--- |
| **Elide** | *SPHEREx Data Pipeline Specialist* | [`spherex_data_pipeline_elide/`](spherex_data_pipeline_elide/) | Connection with NASA/IPAC IRSA (TAP/SIA/IBE), extraction of Multi-Extension FITS (MEF), flags masking, WCS parsing, and standardized cutouts. |
| **Etner** | *Scientific / Motion Engine Specialist* | [`scientific_motion_engine_etner/`](scientific_motion_engine_etner/) | Astrometric & temporal engine: WCS reprojection, zodiacal light (ZODI) subtraction, variance-weighted ($\sigma^2$) *Image Differencing*, dipole detection, and kinematic derivation (″/year). |
| **Anghelo** | *Backend, API & Integration Specialist* | [`backend_api_integration_anghelo/`](backend_api_integration_anghelo/) | High-performance asynchronous REST API with FastAPI, background task orchestration, spectral channel grouping, astronomical catalog crossmatching, and PNG image serving. |
| **Andy** | *Frontend & Visualization Specialist* | [`frontend_visualization_andy/`](frontend_visualization_andy/) | Interactive web interface (WiseView/Aladin style) in React + TypeScript + Canvas, multi-mode time viewer (Blink/Difference/Swipe/Hunter), colormaps/stretch controls, i18n (EN/ES), and animated GIF export. |
| **Andre** | *Video & Project Presentation* | Documentation / Pitch / Video | Science communication narrative, challenge scriptwriting, interactive demo recording, video editing, and final project presentation for NASA Space Apps judges. |

---

## 🎯 NASA Challenge Overview: Planet X and SPHEREx

Since 2025, NASA’s **SPHEREx** mission has been mapping the entire sky every six months across **102 near-infrared spectral bands** ($0.75\,\mu\text{m}$ to $5.0\,\mu\text{m}$), imaging over a billion celestial sources. This unprecedented spectral richness makes SPHEREx uniquely sensitive to signatures of water ($H_2O$), carbon monoxide and dioxide ice ($CO, CO_2$), hydrocarbons, and cosmic dust.

However, the sheer volume of data is immense: millions of images and gigabytes of multi-dimensional cubes. Asteroids, comets, nearby stars, brown dwarfs, and outer Solar System planets reveal themselves by shifting angular positions across observation epochs separated by weeks or months.

**Our Solution:** We created a comprehensive, full-stack platform enabling any researcher or citizen scientist to:
1. Enter celestial coordinates (RA, Dec) or select historical benchmark targets.
2. Automatically retrieve multi-extension spectral observations from IRSA across distinct epochs.
3. Reproject and astrometrically align frames onto a shared reference grid using high-precision WCS.
4. Clean and subtract cosmic and zodiacal light backgrounds (*Zodi*).
5. Perform variance-weighted ($\sigma^2$) *Image Differencing* to isolate moving transients from static backgrounds.
6. Visually inspect data through Blink, Difference, Swipe, and interactive Hunter Mode with automated crossmatching against external astronomical catalogs.

---

## 🏛️ System Architecture

The project is built upon a decoupled 4-tier modular architecture:

```mermaid
flowchart TD
    subgraph Layer1["1. Data Pipeline (Elide)"]
        IRSA["NASA / IPAC IRSA<br/>(TAP / SIA / IBE Service)"] -->|Query TAP & SIA| Extractor["spherex_pipeline / irsa.py"]
        Extractor -->|Download MEF / Cutouts| FitsReader["fits_reader.py & masking.py"]
        FitsReader -->|Extract IMAGE, VARIANCE, FLAGS, ZODI, WCS| ObsContract["Standardized Observation Contract"]
    end

    subgraph Layer2["2. Scientific Engine (Etner)"]
        ObsContract --> Preproc["astro_pipeline / normalize.py & subtract_zodi.py"]
        Preproc --> Reproject["WCS Astrometric Reprojection<br/>(reproject_interp)"]
        Reproject --> DiffEngine["difference_imaging.py & gaussian.py<br/>SNR = ΔI / √(σ₁² + σ₂²)"]
        DiffEngine --> DetectPeaks["detect_peaks.py & match_dipoles.py"]
        DetectPeaks --> Kinematics["kinematics.py: Astrometric Derivation (RA, Dec, \"/yr)"]
        Kinematics --> Candidates["AnalysisResult: Validated Candidate List"]
    end

    subgraph Layer3["3. Backend API & Integration (Anghelo)"]
        Candidates --> APIRouter["FastAPI Endpoints (/api/v1/spectral-analyses)"]
        APIRouter --> BgWorker["Background Worker: Async Task Orchestration"]
        BgWorker --> BandMatcher["Spectral Grouping (band_spec.py)"]
        BgWorker --> Crossmatch["SIMBAD / Gaia / JPL SBDB Crossmatch"]
        BgWorker --> PNGGen["Scientific PNG Rendering (asinh stretch)"]
    end

    subgraph Layer4["4. Web Frontend & Visualization (Andy)"]
        APIRouter --> WebApp["React 18 + TypeScript + Vite UI"]
        WebApp --> SkyCanvas["WebGL / 2D High-DPI Canvas SkyViewer"]
        SkyCanvas --> ToolModes["Modes: Normal / Blink / Difference / Swipe"]
        SkyCanvas --> HunterMode["Hunter Mode: Manual Track Marking & Reporting"]
        SkyCanvas --> ExportTool["Animated GIF Export & Candidate JSON Export"]
    end
```

---

## 📂 Deep Dive into the 4 Core Folders

```
nasa-space-challenge-planeta-x-spherex/
├── README.md                              # Master project documentation
├── DESAFIO-NASA-SPACE-APPS.md             # Official NASA challenge prompt & specs
├── ENDPOINT_SPECTRAL_ANALYSIS.md          # Quick reference for API endpoints
│
├── spherex_data_pipeline_elide/           # FOLDER 1: IRSA access & FITS preprocessing
├── scientific_motion_engine_etner/        # FOLDER 2: Scientific engine & motion detection
├── backend_api_integration_anghelo/       # FOLDER 3: FastAPI REST backend & integration
└── frontend_visualization_andy/           # FOLDER 4: Interactive web visualization app
```

---

### 1. `spherex_data_pipeline_elide/` — SPHEREx Scientific Data Pipeline

Handles querying, downloading, decoding, and standardizing astronomical files from official NASA/IPAC IRSA servers.

* **Owner:** Elide
* **Dependencies:** `astropy`, `pyvo`, `numpy`, `scipy`, `pytest`

#### Key Capabilities:
1. **TAP & SIA Astronomical Queries (`irsa.py`):** Executes ADQL queries against the SPHEREx catalog (e.g., QR2/QR3 data releases). Features automated fallback between Table Access Protocol (TAP) and Simple Image Access (SIA).
2. **Resilient Cutout Retrieval (`cutouts.py`):** Sends optimized HTTP requests to the IRSA Image Boundary Endpoint (IBE) requesting targeted cutouts (default `0.05°`), eliminating unnecessary bandwidth overhead from full-size multi-gigabyte FITS.
3. **Multi-Extension FITS (MEF) Parsing (`fits_reader.py`):** Reliably extracts core SPHEREx extensions:
   * `IMAGE`: Calibrated flux in surface brightness units ($MJy/sr$).
   * `VARIANCE` / `ERR`: Formal statistical measurement noise map ($\sigma^2$).
   * `FLAGS` / `DQ`: Bitmask data quality flags (dead, saturated, or cosmic-ray hit pixels).
   * `ZODI`: Modeled line-of-sight interplanetary zodiacal dust emission.
   * `WCS`: World Coordinate System for spatial calibration (RA/Dec) and spectral dispersion mapping (`WCS-WAVE`).
4. **Masking & Array Homogenization (`masking.py`, `pipeline.py`):** Produces boolean `valid_mask` arrays from DQ flags and applies array padding to homogenize frame dimensions without altering native WCS projections.
5. **Integrated Local Demo Dataset (`spherex_pipeline/data/demo/`):** Bundles 5 real observation epochs centered on the Pinwheel Galaxy (M101: RA `210.80227°`, Dec `54.34895°`), enabling full offline development and testing.

#### Core Files:
* [`pipeline.py`](spherex_data_pipeline_elide/spherex_pipeline/pipeline.py): Central entry point for `get_observations()`.
* [`irsa.py`](spherex_data_pipeline_elide/spherex_pipeline/irsa.py): Network connectors for TAP/SIA protocols with NASA IRSA.
* [`fits_reader.py`](spherex_data_pipeline_elide/spherex_pipeline/fits_reader.py): Robust multi-extension FITS file parser.
* [`masking.py`](spherex_data_pipeline_elide/spherex_pipeline/masking.py): Quality flag evaluation and array masking.
* [`spectral_select.py`](spherex_data_pipeline_elide/spherex_pipeline/spectral_select.py): Wavelength alignment filter preventing cross-dispersion discrepancies.

---

### 2. `scientific_motion_engine_etner/` — Scientific Motion Detection Engine

The mathematical, image-processing, and astrometric core that identifies moving and transient sources across multiple observation epochs.

* **Owner:** Etner
* **Dependencies:** `astropy`, `reproject`, `numpy`, `scipy`, `matplotlib`, `pytest`

#### Key Capabilities:
1. **Zodiacal Light Subtraction & Background Normalization (`subtract_zodi.py`, `normalize.py`):**
   * Removes diffuse interplanetary dust emission: $\text{data}_{\text{clean}} = \text{data}_{\text{raw}} - \text{ZODI}$.
   * When variance arrays are absent, computes robust background dispersion using Median Absolute Deviation (MAD):
     $$\sigma = 1.4826 \times \text{median}(|x - \text{median}(x)|)$$
2. **Astrometric WCS Reprojection (`align.py`):**
   * Uses Astropy’s `reproject` library (`reproject_interp`) to map all temporal observations onto a common reference grid ($WCS_{\text{ref}}$), correcting for spacecraft roll, optical field distortion, and telescope pointings.
3. **Variance-Weighted Temporal Image Differencing (`difference.py`, `difference_imaging.py`):**
   * Subtracts consecutive epochs ($t_1, t_2$) while formally propagating statistical uncertainties:
     $$\Delta I = I_{t_2} - I_{t_1}, \qquad \sigma_{\text{diff}} = \sqrt{\sigma_{t_1}^2 + \sigma_{t_2}^2}$$
   * Produces an exact Signal-to-Noise Ratio map: $\text{SNR} = \frac{\Delta I}{\sigma_{\text{diff}}}$.
4. **Dipole Matching & Static Star Veto (`detect_peaks.py`, `match_dipoles.py`):**
   * A moving astronomical source produces a dipole signature in the difference image: a negative trough at $t_1$ and a positive peak at $t_2$.
   * Identifies 2D local extrema exceeding statistical thresholds ($SNR \ge 3.0$), pairs positive/negative dipoles, and enforces an anti-star veto to reject residuals from bright fixed stars.
5. **Kinematic & Astrometric Derivations (`kinematics.py`):**
   * Calculates celestial coordinates (RA, Dec in J2000), total angular displacement in arcseconds ($\Delta\theta''$), and apparent proper motion in arcseconds per year ($''/\text{yr}$).
6. **Benchmark Validation Probes (`challenge_targets/`):**
   * Houses diagnostic routines and summary metrics on all 5 official challenge targets: Barnard’s Star, Epsilon Indi B, WISE 0855-0714, RW Aurigae, and R Draconis.

#### Core Files:
* [`main.py`](scientific_motion_engine_etner/astro_pipeline/main.py): Unified orchestrator for the scientific pipeline.
* [`align.py`](scientific_motion_engine_etner/astro_pipeline/align.py): Astrometric alignment and reprojection via Astropy WCS.
* [`difference.py`](scientific_motion_engine_etner/astro_pipeline/difference.py): Temporal subtraction and formal $\sigma^2$ propagation.
* [`detect_peaks.py`](scientific_motion_engine_etner/astro_pipeline/detect_peaks.py): 2D peak finding above configured SNR limits.
* [`match_dipoles.py`](scientific_motion_engine_etner/astro_pipeline/match_dipoles.py): Motion dipole pairing algorithm.
* [`kinematics.py`](scientific_motion_engine_etner/astro_pipeline/kinematics.py): Pixel-to-sky astrometric transformations and velocity metrics.

---

### 3. `backend_api_integration_anghelo/` — REST Backend API & Integration

Fast, asynchronous intermediary layer connecting Elide’s data extraction with Etner’s scientific engine, managing session state, caching, and serving web-ready payloads to the frontend.

* **Owner:** Anghelo
* **Tech Stack:** Python 3.12, FastAPI, Uvicorn, Docker, PyVO, Astropy, Matplotlib, Pydantic v2

#### Key Capabilities:
1. **Asynchronous RESTful Endpoints (`app/routers/spectral_analysis.py`):**
   * `POST /api/v1/spectral-analyses`: Accepts coordinates (RA, Dec, size, bandpass) and responds in $<200\text{ms}$ with `202 Accepted` and a `session_id`, scheduling heavy computational tasks to a background worker.
   * `GET /api/v1/spectral-analyses/{session_id}`: Provides polling endpoint returning session state (`PENDIENTE`, `EN_PROCESO`, `COMPLETADO`, `ERROR`) and progress (0% to 100%).
   * `GET /api/v1/spectral-analyses/{session_id}/observations`: Structured metadata list of all retrieved exposures (timestamp, detector ID, wavelength in $\mu\text{m}$, product URL).
   * `GET /api/v1/spectral-analyses/{session_id}/images`: Complete index of preview PNG URLs and original FITS download links.
   * `GET /api/v1/spectral-analyses/{session_id}/images/{obs_id}/preview.png`: Direct image streaming service delivering contrast-stretched (*asinh*) 8-bit PNGs ready for immediate browser rendering.
   * `GET /api/v1/spectral-analyses/{session_id}/candidates`: Full candidate payload structured across survey pairs with kinematic metrics.
2. **Spectral Grouping Pipeline (`app/services/band_spec.py`):**
   * Because SPHEREx uses Linear Variable Filters (LVF), wavelengths change across the focal plane. The backend automatically clusters observations into homogeneous spectral channels ($\Delta\lambda \le 0.1\,\mu\text{m}$) so that difference imaging compares matching physical emission regimes.
3. **Automated Catalog Crossmatching (`app/services/catalog_crossmatch.py`):**
   * Queries SIMBAD, Gaia DR3, and JPL Small-Body Database (SBDB) to determine whether a moving candidate is a known asteroid, a high-proper-motion star, or an uncataloged new discovery.
4. **Disk Cache with Time-to-Live (TTL):**
   * Configurable local file caching (`CACHE_TTL_HOURS=24`) to eliminate repeated FITS downloads from NASA IRSA.

#### Core Files:
* [`main.py`](backend_api_integration_anghelo/main.py): FastAPI app instance, middleware configuration, and CORS setup.
* [`app/routers/spectral_analysis.py`](backend_api_integration_anghelo/app/routers/spectral_analysis.py): Route declarations and session status handlers.
* [`app/services/real_spherex_pipeline.py`](backend_api_integration_anghelo/app/services/real_spherex_pipeline.py): Bridge uniting Elide's FITS downloader with Etner's `astro_pipeline`.
* [`app/services/band_spec.py`](backend_api_integration_anghelo/app/services/band_spec.py): Spectral channel grouping logic across SPHEREx's 102 bands.
* [`app/services/catalog_crossmatch.py`](backend_api_integration_anghelo/app/services/catalog_crossmatch.py): External catalog querying and candidate tagging.
* [`Dockerfile`](backend_api_integration_anghelo/Dockerfile) and [`compose.yaml`](backend_api_integration_anghelo/compose.yaml): Ready-to-deploy containerization specs.

---

### 4. `frontend_visualization_andy/` — Interactive Web Visualization & Sky Explorer

Modern astronomical web application inspired by tools like WiseView, Legacy Survey Sky Viewer, Aladin, and Backyard Worlds.

* **Owner:** Andy
* **Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS / Vanilla Canvas API, Lucide Icons, `gifenc`

#### Key Capabilities:
1. **Hardware-Accelerated Canvas Sky Viewer (`SkyViewerCanvas.tsx`):**
   * Lag-free rendering of astronomical frames with full sub-pixel precision.
   * Smooth panning, mouse-wheel zooming, and full touch-gesture support (pinch-to-zoom) for mobile phones and tablets.
   * Astrometric orientation overlay (North / East compass), dynamic arcsecond scale bar, and celestial RA/Dec grid (`G`).
2. **Advanced Temporal Visualization Modes:**
   * **Original Mode (`O`):** Standard single-epoch inspection.
   * **Blink Mode (`B`):** Automatic rapid cycling between consecutive epochs at adjustable speeds (0.5×, 1×, 2×), replicating the optical blink comparator technique used by Clyde Tombaugh to discover Pluto.
   * **Difference Mode (`D`):** Visualization of subtraction frames with diverging colormaps highlighting negative/positive flux changes.
   * **Swipe Split Mode (`S`):** Interactive split-view curtain allowing direct before/after sliding comparison between reference and active epochs.
3. **Citizen Science Hunter Mode (`HunterPanel.tsx` / `H`):**
   * Allows users to manually click and track moving points of light across epochs.
   * Calculates displacement vectors, position angles, and motion in $''/\text{yr}$ on the fly.
   * **"Check in Catalogs"** button: cross-references marked coordinates with SIMBAD and JPL Horizons, rendering instant verdicts: *Known Object*, *Matches Algorithm*, or *Possible Discovery!*.
   * Generates a structured, copyable JSON report for scientific submission.
4. **Client-Side Image Manipulation (`ImageControls.tsx`):**
   * Dynamic histogram stretching: Linear, Square Root, Logarithmic, and Inverse Hyperbolic Sine (*asinh*).
   * Real-time brightness, contrast, color inversion, and palette selection (Grayscale, Viridis, Plasma, Inferno, Cool, Colorblind-friendly).
5. **In-Browser Animated GIF Export (`gif.ts`):**
   * Encodes and downloads client-rendered animated GIFs of the active blink or difference sequence directly from the HTML5 Canvas.
6. **Bilingual Internationalization (i18n):**
   * Fully localized in English and Spanish with instant switching via the top navigation bar 🌐, saving user preferences to `localStorage`.
7. **Dual-Mode Operation (Mock vs. Live API):**
   * Operates either with a standalone procedurally generated synthetic sky simulation for offline demoing, or with the live FastAPI backend via `VITE_API_MODE=http`.

#### Core Files:
* [`src/App.tsx`](frontend_visualization_andy/src/App.tsx): Main application state and layout manager.
* [`src/components/SkyViewerCanvas.tsx`](frontend_visualization_andy/src/components/SkyViewerCanvas.tsx): Canvas rendering engine with transforms and overlays.
* [`src/components/Timeline.tsx`](frontend_visualization_andy/src/components/Timeline.tsx): Epoch scrubber and playback controller.
* [`src/components/HunterPanel.tsx`](frontend_visualization_andy/src/components/HunterPanel.tsx): Manual orbit tracking and citizen-science reporting panel.
* [`src/components/ImageControls.tsx`](frontend_visualization_andy/src/components/ImageControls.tsx): Dynamic image stretch, contrast, and colormap toolbar.
* [`src/api/httpApi.ts`](frontend_visualization_andy/src/api/httpApi.ts): HTTP client connecting the frontend to Anghelo's FastAPI endpoints.

---

## 🔬 Data Flow & Integration Contracts

Communication across all 4 components is governed by standardized contracts:

### 1. `Observation` Contract (Elide → Etner / Backend)
```python
class Observation:
    id: str                         # Unique exposure identifier
    timestamp: str                  # ISO-8601 (e.g., "2025-06-06T11:22:23.837Z")
    ra: float                       # Requested central RA in degrees
    dec: float                      # Requested central Dec in degrees
    detector: int                   # SPHEREx detector index (1 through 6)
    wavelength: float               # Central band wavelength in micrometers (μm)
    bandwidth: float                # Spectral bandpass width in micrometers (μm)
    image: np.ndarray               # 2D calibrated flux array (MJy/sr)
    variance: np.ndarray            # 2D formal statistical variance array (σ²)
    flags: np.ndarray               # 2D data quality bitmask array
    zodi: np.ndarray                # 2D zodiacal light background model
    valid_mask: np.ndarray          # 2D boolean mask of clean scientific pixels
    wcs: astropy.wcs.WCS            # Astropy 2D spatial World Coordinate System
```

### 2. `Candidate` Contract (Etner → Backend → Frontend)
```json
{
  "id": "C-001",
  "ra": 210.80806,
  "dec": 54.35412,
  "displacementArcsec": 202.95,
  "motionArcsecPerYear": 189.28,
  "snr": 18.4,
  "status": "candidate",
  "detections": [
    {
      "observationId": "level2_2025W23_2B_0206_1D2",
      "timestamp": "2025-06-06T11:22:23.837Z",
      "ra": 210.80806,
      "dec": 54.35412,
      "x": 34.2,
      "y": 28.1,
      "snr": 18.4
    }
  ]
}
```

---

## 🚀 Quickstart & Setup Guide

### Prerequisites
* **Python:** 3.11 or 3.12 installed.
* **Node.js:** v18 or newer with `npm`.
* **Docker:** (Optional, recommended for Backend) Docker Desktop & Docker Compose.

---

### Option A: Docker Deployment (Recommended for Backend)

From the project root:
```bash
# 1. Build and run the Backend API container
docker compose up --build -d

# API will be available at http://localhost:8000
# Interactive Swagger docs at http://localhost:8000/docs
```

Next, in a separate terminal, launch the web application:
```bash
cd frontend_visualization_andy
npm install
npm run dev
# The web app will launch at http://localhost:5173
```

---

### Option B: Manual Module-by-Module Setup

#### 1. SPHEREx Data Pipeline (Elide)
```bash
cd spherex_data_pipeline_elide
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

pip install -e ".[dev]"
pytest tests/
```

#### 2. Scientific Motion Engine (Etner)
```bash
cd scientific_motion_engine_etner
python -m venv .venv
.venv\Scripts\activate

pip install -e ".[dev]"
# Run demo pipeline on synthetic/benchmark data:
python -m astro_pipeline
# Run test suite:
pytest tests/
```

#### 3. Backend API (Anghelo)
```bash
cd backend_api_integration_anghelo
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### 4. Web Frontend (Andy)
```bash
cd frontend_visualization_andy
npm install

# Connect to the local backend API by creating .env.local:
# VITE_API_MODE=http
# VITE_API_URL=http://localhost:8000

npm run dev
```

---

## 🎯 NASA Challenge Benchmark Targets

Our engine has been validated against all 5 primary benchmark targets specified in the NASA Space Apps Challenge:

| Benchmark Target | Coordinates (RA, Dec) | Object Class | Scientific Phenomenon |
| :--- | :--- | :--- | :--- |
| **Barnard’s Star** | `17h 57m 48.5s, +04° 41′ 36″` | Nearby red dwarf | Highest known proper motion in the sky (~$10.3''/\text{yr}$). |
| **Epsilon Indi B** | `22h 04m 10.5s, -56° 46′ 58″` | Binary brown dwarf system | Fast co-moving cool infrared sources. |
| **WISE 0855-0714** | `08h 55m 10.8s, -07° 14′ 42.5″` | Sub-stellar cold brown dwarf | Invisible in optical surveys; prominent in SPHEREx thermal infrared bands. |
| **RW Aurigae** | `05h 07m 49.5s, +30° 24′ 05″` | T Tauri variable star | Infrared flux fluctuations driven by circumstellar dust accretion disks. |
| **R Draconis** | `16h 32m 40.2s, +66° 45′ 18″` | Mira-type variable star | High-amplitude stellar thermal pulsations. |

---

## ⌨️ Keyboard Shortcuts for the Sky Viewer

| Key | Action |
| :---: | :--- |
| `←` / `→` | Step to Previous / Next Observation Epoch |
| `Space` | Play / Pause Automatic Epoch Playback |
| `O` | Switch to Original Mode |
| `B` | Switch to Blink Mode |
| `D` | Switch to Difference Mode |
| `S` | Switch to Swipe Split-View Mode |
| `H` | Toggle Citizen Science Hunter Mode |
| `G` | Toggle Astrometric RA/Dec Coordinate Grid |
| `K` | Toggle Overlay of Known Catalog Objects |
| `F` | Toggle Fullscreen Mode |
| `?` | Open Help & Keyboard Shortcuts Modal |

---

## 📜 Acknowledgments & Data Attribution

Developed for the **NASA Space Apps Challenge 2026**.

We express our sincere gratitude to the **NASA SPHEREx Mission Team**, the **California Institute of Technology (Caltech)**, the **Jet Propulsion Laboratory (JPL)**, and the **NASA/IPAC Infrared Science Archive (IRSA)** for providing public access to data releases QR2 and QR3.
