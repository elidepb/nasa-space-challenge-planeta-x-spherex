/**
 * Contratos compartidos con el backend.
 *
 * `ObservationSummary` replica `Observation.to_summary()` del pipeline de Elide
 * (spherex_data_pipeline_elide/spherex_pipeline/models.py). Las matrices
 * científicas no viajan en JSON: el front solo recibe URLs de imágenes ya
 * renderizadas mediante `GET /analysis/{id}/images`.
 */

export interface RegionQuery {
  ra: number
  dec: number
  /** Lado del cutout en grados (igual que `size` en get_observations). */
  size: number
  qr?: string
  bandpass?: string
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

export interface AnalysisImages {
  /** Tamaño de la cuadrícula común (reproyectada) en píxeles. */
  width: number
  height: number
  pixelScaleArcsec: number
  epochs: EpochImage[]
  differences: DifferenceImage[]
}

export interface AnalysisResult {
  analysis: AnalysisInfo
  observations: ObservationSummary[]
  candidates: Candidate[]
  images: AnalysisImages
  knownObjects: KnownObject[]
}
