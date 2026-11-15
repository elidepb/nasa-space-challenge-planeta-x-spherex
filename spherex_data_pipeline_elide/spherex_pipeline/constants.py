"""Constantes del pipeline SPHEREx / IRSA."""

from __future__ import annotations

from pathlib import Path

IRSA_TAP_URL = "https://irsa.ipac.caltech.edu/TAP"
IRSA_TAP_SYNC_URL = "https://irsa.ipac.caltech.edu/TAP/sync"
IRSA_BASE_URL = "https://irsa.ipac.caltech.edu/"
IRSA_SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
IBE_SPHEREX_DATA_MARKER = "/ibe/data/spherex/"
SPHEREX_S3_HTTPS_BASE = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com"

KNOWN_RELEASES = {
    "qr2": {"sia_collection": "spherex_qr2", "uri_fragment": "/spherex/qr2/"},
    "qr3": {"sia_collection": "spherex_qr3", "uri_fragment": "/spherex/qr3/"},
    "qr2_deep": {"sia_collection": "spherex_qr2_deep", "uri_fragment": "/spherex/qr2_deep/"},
    "qr3_deep": {"sia_collection": "spherex_qr3_deep", "uri_fragment": "/spherex/qr3_deep/"},
}

KNOWN_BANDPASSES = tuple(f"SPHEREx-D{i}" for i in range(1, 7))
DEFAULT_QR = "qr2"
DEFAULT_BANDPASS = "SPHEREx-D4"
DEFAULT_SOURCE = "irsa"
DEFAULT_PIPELINE_METHOD = "spectral"
DEFAULT_SPECTRAL_GROUP = 7

# λ/Δλ del Level-2 salen del WCS espectral del producto, no de CWAVE/CBAND.
SPECTRAL_UNIT = "μm"
SPECTRAL_CALIBRATION_QUALITY = "approximate"
SPECTRAL_CALIBRATION_SOURCE_WCS_WAVE = "WCS-WAVE"

# Región demo: galaxia Pinwheel (M101), misma que el tutorial oficial de cutouts IRSA.
DEMO_RA = 7.93770
DEMO_DEC = -10.97988
DEMO_SIZE_DEG = 0.85
DEMO_BANDPASS = "SPHEREx-D5"
DEMO_DETECTOR = 2
DEMO_WAVELENGTH_UM = 1.35
DEMO_PIXEL_SCALE_ARCSEC = 6.2
DEMO_NPIX = 64
DEMO_N_EPOCHS = 5

REMOTE_TIMEOUT_S = 4
DOWNLOAD_RETRIES = 3
DEFAULT_MAX_WORKERS = 8

# Bits de FLAGS (Table 10 / encabezado MP_* de SPHEREx).
# El número es el índice de bit, no el valor decimal.
FLAG_BITS = {
    "TRANSIENT": 0,
    "OVERFLOW": 1,
    "SUR_ERROR": 2,
    "PHANTOM": 4,
    "REFERENCE": 5,
    "NONFUNC": 6,
    "DICHROIC": 7,
    "MISSING_DATA": 9,
    "HOT": 10,
    "COLD": 11,
    "FULLSAMPLE": 12,
    "PHANMISS": 14,
    "NONLINEAR": 15,
    "PERSIST": 17,
    "OUTLIER": 19,
    "SOURCE": 21,
}

# Píxeles que no deben usarse en análisis científico inicial.
INVALID_FLAG_NAMES = (
    "TRANSIENT",
    "OVERFLOW",
    "SUR_ERROR",
    "PHANTOM",
    "REFERENCE",
    "NONFUNC",
    "DICHROIC",
    "MISSING_DATA",
    "HOT",
    "COLD",
    "NONLINEAR",
    "PERSIST",
    "OUTLIER",
)

DETECTOR_WAVELENGTH_UM = {
    1: 0.92,
    2: 1.36,
    3: 2.02,
    4: 3.12,
    5: 4.12,
    6: 4.71,
}

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DEMO_DIR = PACKAGE_DIR / "data" / "demo"
CACHE_DIR = PROJECT_DIR / "data" / "cache"
