/**
 * Rangos y bins espectrales alineados con Elide
 * (`spherex_pipeline/spectral_select.py` → DETECTOR_RANGES / get_detector_bins).
 */

export const BANDPASSES = [
  'SPHEREx-D1',
  'SPHEREx-D2',
  'SPHEREx-D3',
  'SPHEREx-D4',
  'SPHEREx-D5',
  'SPHEREx-D6',
] as const

export type Bandpass = (typeof BANDPASSES)[number]

export const N_SPECTRAL_GROUPS = 17
export const DEFAULT_BANDPASS: Bandpass = 'SPHEREx-D2'
export const DEFAULT_SPECTRAL_GROUP = 7

/** μm — mismos límites que el pipeline de Elide. */
export const DETECTOR_RANGES: Record<Bandpass, readonly [number, number]> = {
  'SPHEREx-D1': [0.75, 1.09],
  'SPHEREx-D2': [1.088, 1.656],
  'SPHEREx-D3': [1.63, 2.41],
  'SPHEREx-D4': [2.42, 3.82],
  'SPHEREx-D5': [3.83, 4.41],
  'SPHEREx-D6': [4.42, 5.0],
}

export interface SpectralBin {
  groupId: number
  wlMin: number
  wlMax: number
  wlCenter: number
}

export function isBandpass(value: string): value is Bandpass {
  return (BANDPASSES as readonly string[]).includes(value)
}

export function normalizeBandpass(value: string | undefined | null): Bandpass {
  return value && isBandpass(value) ? value : DEFAULT_BANDPASS
}

export function clampSpectralGroup(group: number | undefined | null): number {
  if (group == null || !Number.isFinite(group)) return DEFAULT_SPECTRAL_GROUP
  return Math.min(N_SPECTRAL_GROUPS, Math.max(1, Math.round(group)))
}

export function detectorNumber(bandpass: string): number {
  const m = /^SPHEREx-D([1-6])$/.exec(bandpass)
  return m ? Number(m[1]) : 2
}

export function getDetectorBins(bandpass: string, nBins = N_SPECTRAL_GROUPS): SpectralBin[] {
  const key = normalizeBandpass(bandpass)
  const [wMin, wMax] = DETECTOR_RANGES[key]
  const step = (wMax - wMin) / nBins
  return Array.from({ length: nBins }, (_, i) => ({
    groupId: i + 1,
    wlMin: +(wMin + i * step).toFixed(6),
    wlMax: +(wMin + (i + 1) * step).toFixed(6),
    wlCenter: +(wMin + (i + 0.5) * step).toFixed(6),
  }))
}

export function getSpectralBin(bandpass: string, group: number): SpectralBin {
  const bins = getDetectorBins(bandpass)
  return bins[clampSpectralGroup(group) - 1]
}

/** Ancho de banda aproximado del canal (μm). */
export function approximateBandwidth(bandpass: string): number {
  const key = normalizeBandpass(bandpass)
  const [wMin, wMax] = DETECTOR_RANGES[key]
  return +((wMax - wMin) / N_SPECTRAL_GROUPS).toFixed(6)
}

/** Canal (1–17) más cercano a una λ dentro de un detector. */
export function groupNearWavelength(bandpass: string, wavelengthUm: number): number {
  const bins = getDetectorBins(bandpass)
  let best = bins[0]
  let bestDist = Infinity
  for (const bin of bins) {
    const d = Math.abs(bin.wlCenter - wavelengthUm)
    if (d < bestDist) {
      bestDist = d
      best = bin
    }
  }
  return best.groupId
}

/**
 * Capas científicas resaltables (features IR típicas de SPHEREx).
 * El `group` apunta al canal del detector donde la feature es más visible.
 */
export type SpectralFeatureId = 'hydrogen' | 'gases' | 'dust'

export interface SpectralFeature {
  id: SpectralFeatureId
  /** Longitud de onda de referencia (μm). */
  wavelengthUm: number
  bandpass: Bandpass
  group: number
  /** Color CSS del overlay (RGB). */
  color: [number, number, number]
}

export const SPECTRAL_FEATURES: SpectralFeature[] = [
  {
    id: 'hydrogen',
    // Paβ ~1.28 μm
    wavelengthUm: 1.282,
    bandpass: 'SPHEREx-D2',
    group: groupNearWavelength('SPHEREx-D2', 1.282),
    color: [80, 220, 255],
  },
  {
    id: 'gases',
    // H2O ice / organics mid-IR ~3.0 μm
    wavelengthUm: 3.0,
    bandpass: 'SPHEREx-D4',
    group: groupNearWavelength('SPHEREx-D4', 3.0),
    color: [120, 255, 140],
  },
  {
    id: 'dust',
    // Continuum / PAH / warm dust ~4.6 μm
    wavelengthUm: 4.6,
    bandpass: 'SPHEREx-D6',
    group: groupNearWavelength('SPHEREx-D6', 4.6),
    color: [255, 170, 70],
  },
]

/** Targets de prueba del challenge Planet X / SPHEREx (coords J2000). */
export const CHALLENGE_TARGETS: {
  id: string
  labelKey: string
  query: { ra: number; dec: number; size: number; bandpass?: Bandpass; group?: number }
}[] = [
  {
    id: 'wise0855',
    labelKey: 'search.presets.wise0855',
    // WISE 0855−0714 — brown dwarf del “first hour”
    query: { ra: 133.795, dec: -7.24514, size: 0.05, bandpass: 'SPHEREx-D2', group: DEFAULT_SPECTRAL_GROUP },
  },
  {
    id: 'barnard',
    labelKey: 'search.presets.barnard',
    query: { ra: 269.45208, dec: 4.69339, size: 0.05, bandpass: 'SPHEREx-D2', group: DEFAULT_SPECTRAL_GROUP },
  },
  {
    id: 'epsIndiB',
    labelKey: 'search.presets.epsIndiB',
    query: { ra: 331.072, dec: -56.7859, size: 0.05, bandpass: 'SPHEREx-D3', group: DEFAULT_SPECTRAL_GROUP },
  },
  {
    id: 'rwAur',
    labelKey: 'search.presets.rwAur',
    query: { ra: 76.95653, dec: 30.40144, size: 0.05, bandpass: 'SPHEREx-D4', group: DEFAULT_SPECTRAL_GROUP },
  },
  {
    id: 'rDra',
    labelKey: 'search.presets.rDra',
    query: { ra: 268.13958, dec: 61.53, size: 0.05, bandpass: 'SPHEREx-D5', group: DEFAULT_SPECTRAL_GROUP },
  },
]
