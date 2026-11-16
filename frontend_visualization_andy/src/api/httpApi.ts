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

interface RapidAnalysisEpoch {
  obs_id: string
  mjd: number
  timestamp: string
  wavelength_um: number
  original_png: string
  residual_png: string
}

interface RapidAnalysisCandidate {
  id: string
  ra_deg: number
  dec_deg: number
  x1_px: number
  y1_px: number
  x2_px: number
  y2_px: number
  snr: number
  displacement_arcsec: number
  velocity_arcsec_yr: number
}

interface RapidAnalysisResponse {
  ra: number
  dec: number
  size_arcsec: number
  band: string
  width?: number
  height?: number
  wcs_header: Record<string, unknown>
  epochs: RapidAnalysisEpoch[]
  candidates: RapidAnalysisCandidate[]
}

interface CachedResult {
  info: AnalysisInfo
  observations: ObservationSummary[]
  candidates: Candidate[]
  images: AnalysisImages
}

export function createHttpApi(baseUrl: string): SpherexApi {
  const root = baseUrl.replace(/\/$/, '')
  const cache = new Map<string, CachedResult>()

  return {
    async createAnalysis(query: RegionQuery): Promise<AnalysisInfo> {
      const sessionId = `analysis-${Date.now()}`
      const band = (query.bandpass ?? 'D1').replace(/^SPHEREx-/i, '')
      const sizeArcsec = Math.round((query.size ?? 0.05) * 3600)
      const bandIndex = query.bands?.[0]
      const bandParam = bandIndex ? `&band_index=${bandIndex}` : ''
      const wl = bandIndex ? Number((0.75 + ((Math.max(1, Math.min(102, bandIndex)) - 1) / 101) * (5.0 - 0.75)).toFixed(4)) : null
      const wlParam = wl ? `&wavelength_um=${wl}` : ''
      const url = `${root}/api/v1/analyze?ra=${query.ra}&dec=${query.dec}&size=${sizeArcsec}&band=${encodeURIComponent(band)}${bandParam}${wlParam}`

      let res: Response
      try {
        const [fetchRes] = await Promise.all([
          fetch(url),
          new Promise((r) => setTimeout(r, 400)), // Delay perceptible para mostrar pantalla de carga
        ])
        res = fetchRes
      } catch {
        throw new ApiError(translate('errors.connection', { url: root }))
      }

      if (!res.ok) {
        let detail = res.statusText
        try {
          const body = await res.json()
          detail = body.detail ?? detail
        } catch {
          // ignore non-json
        }
        throw new ApiError(String(detail), res.status)
      }

      const data = (await res.json()) as RapidAnalysisResponse
      const createdAt = new Date().toISOString()
      const info: AnalysisInfo = {
        id: sessionId,
        status: 'completed',
        region: query,
        createdAt,
        progress: 1.0,
        message: `Análisis rápido completado (${data.epochs.length} épocas, ${data.candidates.length} candidatos)`,
      }

      const w = data.width && data.width > 0 ? data.width : 64
      const h = data.height && data.height > 0 ? data.height : 64
      const observations: ObservationSummary[] = data.epochs.map((ep, idx) => ({
        id: ep.obs_id,
        timestamp: ep.timestamp || new Date(Date.now() - (data.epochs.length - idx) * 86400000).toISOString(),
        ra: data.ra,
        dec: data.dec,
        detector: data.band,
        wavelength: ep.wavelength_um,
        bandwidth: 0.03,
        wavelength_source: 'WCS-WAVE',
        bandwidth_source: null,
        spectral_calibration_source: 'WCS-WAVE',
        spectral_calibration_quality: 'approximate',
        spectral_unit: 'μm',
        fits_source: ep.obs_id,
        shape: [h, w],
        n_invalid_pixels: 0,
        metadata: { mjd: ep.mjd },
      }))

      const nEpochs = data.epochs.length
      const candidates: Candidate[] = data.candidates.map((c) => {
        // Interpolar detecciones para todas las épocas intermedias (movimiento propio lineal)
        const detections = data.epochs.map((ep, i) => {
          const frac = nEpochs > 1 ? i / (nEpochs - 1) : 0
          const curX = c.x1_px + (c.x2_px - c.x1_px) * frac
          const curY = c.y1_px + (c.y2_px - c.y1_px) * frac
          return {
            observationId: ep.obs_id,
            timestamp: ep.timestamp ?? '',
            ra: c.ra_deg,
            dec: c.dec_deg,
            x: curX,
            y: curY,
            snr: c.snr,
          }
        })

        return {
          id: c.id,
          ra: c.ra_deg,
          dec: c.dec_deg,
          snr: c.snr,
          displacementArcsec: c.displacement_arcsec,
          motionArcsecPerYear: c.velocity_arcsec_yr,
          status: 'candidate' as const,
          detections,
        }
      })

      const images: AnalysisImages = {
        width: w,
        height: h,
        pixelScaleArcsec: data.size_arcsec / w,
        epochs: data.epochs.map((ep) => ({
          observationId: ep.obs_id,
          url: ep.original_png,
          residualUrl: ep.residual_png,
        })),
        differences: data.epochs.map((ep) => ({
          observationId: ep.obs_id,
          referenceId: data.epochs[0]?.obs_id ?? ep.obs_id,
          url: ep.residual_png,
        })),
      }

      cache.set(sessionId, { info, observations, candidates, images })
      return info
    },

    async getAnalysis(id: string): Promise<AnalysisInfo> {
      const c = cache.get(id)
      if (c) return c.info
      return {
        id,
        status: 'completed',
        region: { ra: 0, dec: 0, size: 0.05 },
        createdAt: new Date().toISOString(),
      }
    },

    async getObservations(id: string): Promise<ObservationSummary[]> {
      return cache.get(id)?.observations ?? []
    },

    async getCandidates(id: string): Promise<Candidate[]> {
      return cache.get(id)?.candidates ?? []
    },

    async getImages(id: string): Promise<AnalysisImages> {
      return (
        cache.get(id)?.images ?? {
          width: 64,
          height: 64,
          pixelScaleArcsec: 6.2,
          epochs: [],
          differences: [],
        }
      )
    },

    async getKnownObjects(_id: string): Promise<KnownObject[]> {
      return []
    },
  }
}
