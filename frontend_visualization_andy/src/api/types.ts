import type {
  AnalysisImages,
  AnalysisInfo,
  Candidate,
  KnownObject,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'

/** API del front; el adaptador HTTP habla con /api/v1/spectral-analyses. */
export interface SpherexApi {
  /** POST /api/v1/spectral-analyses → AnalysisInfo */
  createAnalysis(query: RegionQuery): Promise<AnalysisInfo>
  /** GET /api/v1/spectral-analyses/{session_id} */
  getAnalysis(id: string): Promise<AnalysisInfo>
  /** GET …/observations */
  getObservations(id: string): Promise<ObservationSummary[]>
  /** GET …/candidates (pairs aplanados) */
  getCandidates(id: string): Promise<Candidate[]>
  /** GET …/images → AnalysisImages (epochs desde preview_png_url) */
  getImages(id: string): Promise<AnalysisImages>
  /** Known objects (aún no en backend → []) */
  getKnownObjects(id: string): Promise<KnownObject[]>
}

export class ApiError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}
