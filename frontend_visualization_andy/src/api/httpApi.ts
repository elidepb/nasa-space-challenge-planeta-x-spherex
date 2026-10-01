import { translate } from '../i18n'
import type {
  AnalysisImages,
  AnalysisInfo,
  Candidate,
  KnownObject,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'
import { ApiError, type SpherexApi } from './types'

export function createHttpApi(baseUrl: string): SpherexApi {
  const root = baseUrl.replace(/\/$/, '')

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response
    try {
      response = await fetch(`${root}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...init?.headers },
      })
    } catch {
      throw new ApiError(translate('errors.connection', { url: root }))
    }
    if (!response.ok) {
      let detail = response.statusText
      try {
        const body = await response.json()
        detail = body.detail ?? body.message ?? detail
      } catch {
        // cuerpo no JSON
      }
      throw new ApiError(String(detail), response.status)
    }
    return response.json() as Promise<T>
  }

  const absolutize = (url: string) => (/^(https?:|data:|blob:)/.test(url) ? url : `${root}${url}`)

  return {
    createAnalysis: (query: RegionQuery) =>
      request<AnalysisInfo>('/analysis', { method: 'POST', body: JSON.stringify(query) }),
    getAnalysis: (id) => request<AnalysisInfo>(`/analysis/${id}`),
    getObservations: (id) => request<ObservationSummary[]>(`/analysis/${id}/observations`),
    getCandidates: (id) => request<Candidate[]>(`/analysis/${id}/candidates`),
    getKnownObjects: async (id) => {
      try {
        return await request<KnownObject[]>(`/analysis/${id}/known-objects`)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return []
        throw err
      }
    },
    getImages: async (id) => {
      const images = await request<AnalysisImages>(`/analysis/${id}/images`)
      return {
        ...images,
        epochs: images.epochs.map((e) => ({ ...e, url: absolutize(e.url) })),
        differences: images.differences.map((d) => ({ ...d, url: absolutize(d.url) })),
      }
    },
  }
}
