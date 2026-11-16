from dataclasses import dataclass

TOTAL_BANDS = 102
MIN_WAVELENGTH_UM = 0.75
MAX_WAVELENGTH_UM = 5.00
BANDS_PER_DETECTOR = 17


@dataclass(frozen=True)
class BandSpec:
    band_index: int
    detector: str
    wavelength_um: float


def resolve_band_spec(
    band_index: int | None = None,
    wavelength_um: float | None = None,
    detector: str | None = None,
) -> BandSpec:
    if band_index is not None:
        idx = max(1, min(TOTAL_BANDS, int(band_index)))
    elif wavelength_um is not None:
        t = (float(wavelength_um) - MIN_WAVELENGTH_UM) / (
            MAX_WAVELENGTH_UM - MIN_WAVELENGTH_UM
        )
        idx = max(1, min(TOTAL_BANDS, round(t * (TOTAL_BANDS - 1)) + 1))
    elif detector:
        clean_det = detector.upper().replace("SPHEREX-", "").strip()
        if clean_det.startswith("D") and clean_det[1:].isdigit():
            det_num = max(1, min(6, int(clean_det[1:])))
            idx = (det_num - 1) * BANDS_PER_DETECTOR + 1
        else:
            idx = 1
    else:
        idx = 1

    det_num = min(6, max(1, (idx - 1) // BANDS_PER_DETECTOR + 1))
    det_str = f"D{det_num}"
    t = (idx - 1) / (TOTAL_BANDS - 1)
    wl = round(MIN_WAVELENGTH_UM + t * (MAX_WAVELENGTH_UM - MIN_WAVELENGTH_UM), 4)
    return BandSpec(band_index=idx, detector=det_str, wavelength_um=wl)
