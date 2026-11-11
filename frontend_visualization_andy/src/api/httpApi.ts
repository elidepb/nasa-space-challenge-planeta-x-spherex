import { translate } from '../i18n'
import type {
  AnalysisInfo,
  KnownObject,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'
import { ApiError, type SpherexApi } from './types'
import {
  mapCandidatesWire,
  mapCreateToAnalysisInfo,
  mapImagesWire,
  mapObservaciones,
  mapStatusToAnalysisInfo,
  SPECTRAL_ANALYSES_PATH,
  toSpectralAnalysisRequest,
  type AnalysisCreateWire,
  type CandidateResponseWire,
  type ImageListWire,
  type ObservationWire,
  type SessionStatusWire,
} from './spectralAnalysis'

interface SessionCache {
  region: RegionQuery
  info: AnalysisInfo
  observations: ObservationSummary[]
  createdAt: string
}

export function createHttpApi(baseUrl: string): SpherexApi {
  const root = baseUrl.replace(/\/$/, '')
  const sessions = new Map<string, SessionCache>()

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
    // 202 Accepted es la respuesta nominal del create.
    if (!response.ok) {
      let detail: unknown = response.statusText
      try {
        const body = await response.json()
        detail = body.detail ?? body.message ?? detail
      } catch {
        // cuerpo no JSON
      }
      throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  const absolutize = (url: string) => (/^(https?:|data:|blob:)/.test(url) ? url : `${root}${url}`)

  function sessionPath(id: string, suffix = '') {
    const base = `${SPECTRAL_ANALYSES_PATH}/${encodeURIComponent(id)}`
    return suffix ? `${base}/${suffix.replace(/^\//, '')}` : base
  }

  function putCache(
    id: string,
    patch: Partial<SessionCache> & Pick<SessionCache, 'region' | 'info' | 'createdAt'>,
  ) {
    const prev = sessions.get(id)
    sessions.set(id, {
      observations: patch.observations ?? prev?.observations ?? [],
      region: patch.region,
      info: patch.info,
      createdAt: patch.createdAt,
    })
  }

  return {
    async createAnalysis(query: RegionQuery) {
      const body = toSpectralAnalysisRequest(query)
      const wire = await request<AnalysisCreateWire>(SPECTRAL_ANALYSES_PATH, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      const region: RegionQuery = {
        ...query,
        size: body.size_deg,
        bandpass: body.bandpass,
        group: body.spectral_group,
      }
      const createdAt = new Date().toISOString()
      const info = mapCreateToAnalysisInfo(wire, region, createdAt)
      const observations = mapObservaciones(wire.observaciones, region)
      putCache(info.id, { region, info, observations, createdAt })
      return info
    },

    async getAnalysis(id) {
      const cached = sessions.get(id)
      const wire = await request<SessionStatusWire>(sessionPath(id))
      const region = cached?.region ?? { ra: 0, dec: 0, size: 0.85 }
      const createdAt = cached?.createdAt ?? new Date().toISOString()
      const info = mapStatusToAnalysisInfo(wire, region, createdAt)
      putCache(id, { region, info, createdAt, observations: cached?.observations })
      return info
    },

    async getObservations(id) {
      const cached = sessions.get(id)
      const wire = await request<ObservationWire[]>(sessionPath(id, 'observations'))
      const region = cached?.region ?? { ra: 0, dec: 0, size: 0.85 }
      const observations = mapObservaciones(wire, region)
      if (cached) putCache(id, { ...cached, observations })
      return observations
    },

    getCandidates: async (id) => {
      try {
        const wire = await request<CandidateResponseWire>(sessionPath(id, 'candidates'))
        return mapCandidatesWire(wire)
      } catch (err) {
        if (err instanceof ApiError && (err.status === 400 || err.status === 404)) return []
        throw err
      }
    },

    getKnownObjects: async (_id) => {
      // El backend aún no expone known-objects.
      void _id
      return [] as KnownObject[]
    },

    getImages: async (id) => {
      const wire = await request<ImageListWire>(sessionPath(id, 'images'))
      return mapImagesWire(wire, absolutize)
    },
  }
}
