/**
 * Contratos de UI. Wire HTTP real en `api/spectralAnalysis.ts`
 * (doc: `backend_api_integration_anghelo/README.md`):
 *
 *   POST /api/v1/spectral-analyses
 *     { ra, dec, size_deg, bandpass, spectral_group }
 *   → 202 { session_id, estado, message, spectral_group, observaciones[] }
 *
 *   GET  /api/v1/spectral-analyses/{id}
 *   GET  …/observations | …/images | …/candidates
 */

export interface RegionQuery {
  ra: number
  dec: number
  /** Lado del cutout en grados → wire `size_deg`. */
  size: number
  qr?: string
  /** Detector SPHEREx: SPHEREx-D1 … SPHEREx-D6 → wire `bandpass`. */
  bandpass?: string
  /**
   * Canal espectral 1–17 → wire `spectral_group`.
   * Mismo `group` que Elide. Default del backend: 5; UI default: 7.
   */
  group?: number
  /** Banda global 1–102 (solo 1; el API usa bandpass + spectral_group). */
  bands?: number[]
}

export interface ObservationSummary {
  id: string
  timestamp: string
  ra: number
  dec: number
  detector: number | string
  wavelength: number | null
  bandwidth: number | null
  wavelength_source: string | null
  bandwidth_source: string | null
  spectral_calibration_source: string | null
  spectral_calibration_quality: string
  spectral_unit: string
  fits_source: string
  shape: [number, number] | null
  n_invalid_pixels: number | null
  metadata: Record<string, unknown>
}

export interface CandidateDetection {
  observationId: string
  timestamp: string
  ra: number
  dec: number
  /** Posición en píxeles dentro de la cuadrícula común del análisis. */
  x: number
  y: number
  snr?: number
}

export type CandidateStatus = 'candidate' | 'confirmed' | 'rejected' | 'artifact'

export interface Candidate {
  id: string
  ra: number
  dec: number
  detections: CandidateDetection[]
  displacementArcsec: number
  motionArcsecPerYear: number
  snr: number
  status: CandidateStatus
}

export type KnownObjectType = 'asteroid' | 'comet' | 'planet' | 'satellite'

/** Objeto del Sistema Solar ya catalogado (p. ej. SkyBoT/IMCCE) presente en el campo. */
export interface KnownObject {
  name: string
  type: KnownObjectType
  /** Magnitud visual estimada, si el servicio la entrega. */
  magnitude?: number
  /** Posición predicha en cada época, en la cuadrícula común del análisis. */
  positions: { observationId: string; ra: number; dec: number; x: number; y: number }[]
}

export type AnalysisStatus = 'pending' | 'processing' | 'completed' | 'error'

export interface AnalysisInfo {
  id: string
  status: AnalysisStatus
  region: RegionQuery
  createdAt: string
  /** 0..1, opcional mientras el backend no lo reporte. */
  progress?: number
  message?: string
  error?: string
}

export interface EpochImage {
  observationId: string
  url: string
}

export interface DifferenceImage {
  observationId: string
  referenceId: string
  url: string
}

/** Capa espectral opcional (polvo, gases, H…) para superponer en el visor. */
export interface FeatureLayerImage {
  id: string
  url: string
  /** Color de acento RGB (para leyenda). */
  color: [number, number, number]
  /** Detector / canal sugerido donde la feature destaca. */
  bandpass?: string
  group?: number
  wavelengthUm?: number
}

export interface AnalysisImages {
  /** Tamaño de la cuadrícula común (reproyectada) en píxeles. */
  width: number
  height: number
  pixelScaleArcsec: number
  epochs: EpochImage[]
  differences: DifferenceImage[]
  /** Capas científicas opcionales (mock o backend). */
  featureLayers?: FeatureLayerImage[]
}

export interface AnalysisResult {
  analysis: AnalysisInfo
  observations: ObservationSummary[]
  candidates: Candidate[]
  images: AnalysisImages
  knownObjects: KnownObject[]
}
