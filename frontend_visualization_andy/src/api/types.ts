import type {
  AnalysisImages,
  AnalysisInfo,
  Candidate,
  KnownObject,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'

/** Endpoints mínimos definidos para el backend de Anghelo. */
export interface SpherexApi {
  /** POST /analysis */
  createAnalysis(query: RegionQuery): Promise<AnalysisInfo>
  /** GET /analysis/{id} */
  getAnalysis(id: string): Promise<AnalysisInfo>
  /** GET /analysis/{id}/observations */
  getObservations(id: string): Promise<ObservationSummary[]>
  /** GET /analysis/{id}/candidates */
  getCandidates(id: string): Promise<Candidate[]>
  /** GET /analysis/{id}/images */
  getImages(id: string): Promise<AnalysisImages>
  /** GET /analysis/{id}/known-objects (propuesto: SkyBoT por época, resuelto en el backend) */
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
