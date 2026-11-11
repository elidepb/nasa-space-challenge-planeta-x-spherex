/**
 * Contrato wire del backend Anghelo:
 * `backend_api_integration_anghelo/README.md`
 *
 * Prefijo: `/api/v1/spectral-analyses`
 * El UI interno sigue usando RegionQuery / AnalysisInfo / ObservationSummary /
 * Candidate / AnalysisImages; aquí solo se traduce.
 */

import type {
  AnalysisImages,
  AnalysisInfo,
  AnalysisStatus,
  Candidate,
  CandidateDetection,
  CandidateStatus,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'
import { detectorNumber, normalizeBandpass } from '../lib/spectral'

export const SPECTRAL_ANALYSES_PATH = '/api/v1/spectral-analyses'

/** POST /spectral-analyses */
export interface SpectralAnalysisRequest {
  ra: number
  dec: number
  size_deg: number
  bandpass: string
  spectral_group: number
}

export type BackendSessionEstado = 'EN_PROCESO' | 'COMPLETADO' | 'ERROR' | string

/** ObservationSummarySchema del backend. */
export interface ObservationWire {
  id_exposicion: string
  timestamp: string
  survey_index: number
  wavelength?: number | null
  bandwidth?: number | null
  fits_source: string
  shape?: number[] | null
  n_invalid_pixels?: number | null
}

/** 202 del create. */
export interface AnalysisCreateWire {
  session_id: string
  estado: BackendSessionEstado
  message: string
  spectral_group: number
  observaciones: ObservationWire[]
}

/** GET /spectral-analyses/{id} */
export interface SessionStatusWire {
  session_id: string
  estado: BackendSessionEstado
  progreso_porcentaje: number
  total_observaciones_grupo: number
  observaciones_descargadas: number
  candidatos_detectados: number
  error_detail?: string | null
}

export interface ImageListItemWire {
  obs_id: string
  survey_index: number
  wavelength_um: number
  shape: number[]
  preview_png_url: string
  fits_download_url: string
}

export interface ImageListWire {
  session_id: string
  total_imagenes: number
  imagenes: ImageListItemWire[]
}

export interface CandidateDetectionWire {
  observationId?: string
  observation_id?: string
  timestamp?: string
  ra?: number
  dec?: number
  x?: number
  y?: number
  snr?: number
}

export interface CandidateWire {
  candidate_id: string
  ra: number
  dec: number
  snr: number
  motion_arcsec_yr: number
  displacement_arcsec?: number
  status: string
  detections?: CandidateDetectionWire[]
}

export interface CandidatePairWire {
  survey_pair: number[]
  total_candidatos: number
  candidatos: CandidateWire[]
}

export interface CandidateResponseWire {
  session_id: string
  total_candidatos: number
  pairs: CandidatePairWire[]
}

export function toSpectralAnalysisRequest(query: RegionQuery): SpectralAnalysisRequest {
  return {
    ra: query.ra,
    dec: query.dec,
    size_deg: query.size,
    bandpass: normalizeBandpass(query.bandpass ?? 'SPHEREx-D2'),
    spectral_group: Math.min(17, Math.max(1, Math.round(query.group ?? 7))),
  }
}

export function mapSessionEstado(estado: BackendSessionEstado): AnalysisStatus {
  switch (String(estado).toUpperCase()) {
    case 'EN_PROCESO':
    case 'PROCESSING':
      return 'processing'
    case 'PENDIENTE':
    case 'PENDING':
      return 'pending'
    case 'COMPLETADO':
    case 'COMPLETED':
    case 'LISTO':
      return 'completed'
    case 'ERROR':
    case 'FALLIDO':
      return 'error'
    default:
      return 'processing'
  }
}

export function mapCreateToAnalysisInfo(
  wire: AnalysisCreateWire,
  region: RegionQuery,
  createdAt = new Date().toISOString(),
): AnalysisInfo {
  const status = mapSessionEstado(wire.estado)
  return {
    id: String(wire.session_id),
    status,
    region: { ...region, group: wire.spectral_group, bandpass: region.bandpass },
    createdAt,
    message: wire.message,
    progress: status === 'completed' ? 1 : 0.05,
  }
}

export function mapStatusToAnalysisInfo(
  wire: SessionStatusWire,
  region: RegionQuery,
  createdAt: string,
): AnalysisInfo {
  const status = mapSessionEstado(wire.estado)
  const progress = Math.min(1, Math.max(0, Number(wire.progreso_porcentaje ?? 0) / 100))
  const message =
    status === 'error'
      ? (wire.error_detail ?? 'Error en el análisis')
      : status === 'completed'
        ? `Completado · ${wire.observaciones_descargadas}/${wire.total_observaciones_grupo} obs · ${wire.candidatos_detectados} candidatos`
        : `Procesando · ${wire.observaciones_descargadas}/${wire.total_observaciones_grupo} · ${Math.round(progress * 100)}%`

  return {
    id: String(wire.session_id),
    status,
    region,
    createdAt,
    progress,
    message,
    error: status === 'error' ? (wire.error_detail ?? undefined) : undefined,
  }
}

export function mapObservationWire(
  obs: ObservationWire,
  region: Pick<RegionQuery, 'ra' | 'dec' | 'bandpass'>,
): ObservationSummary {
  const bandpass = normalizeBandpass(region.bandpass)
  const shape =
    Array.isArray(obs.shape) && obs.shape.length >= 2
      ? ([obs.shape[0], obs.shape[1]] as [number, number])
      : null

  return {
    id: obs.id_exposicion,
    timestamp: obs.timestamp && obs.timestamp !== 'n/d' ? obs.timestamp : '',
    ra: region.ra,
    dec: region.dec,
    detector: detectorNumber(bandpass),
    wavelength: obs.wavelength ?? null,
    bandwidth: obs.bandwidth ?? null,
    wavelength_source: obs.wavelength != null ? 'IRSA/FITS' : null,
    bandwidth_source: obs.bandwidth != null ? 'FITS' : null,
    spectral_calibration_source: null,
    spectral_calibration_quality: 'approximate',
    spectral_unit: 'μm',
    fits_source: obs.fits_source ?? '',
    shape,
    n_invalid_pixels: obs.n_invalid_pixels ?? null,
    metadata: {
      survey_index: obs.survey_index,
      banda: bandpass,
    },
  }
}

export function mapObservaciones(
  wire: ObservationWire[] | undefined,
  region: Pick<RegionQuery, 'ra' | 'dec' | 'bandpass'>,
): ObservationSummary[] {
  return (wire ?? [])
    .map((o) => mapObservationWire(o, region))
    .sort((a, b) => {
      const ta = a.timestamp ? Date.parse(a.timestamp) : 0
      const tb = b.timestamp ? Date.parse(b.timestamp) : 0
      if (Number.isFinite(ta) && Number.isFinite(tb) && ta !== tb) return ta - tb
      const sa = Number(a.metadata?.survey_index ?? 0)
      const sb = Number(b.metadata?.survey_index ?? 0)
      return sa - sb
    })
}

function mapCandidateStatus(raw: string | undefined): CandidateStatus {
  switch (String(raw ?? '').toLowerCase()) {
    case 'confirmed':
    case 'validated':
      return 'confirmed'
    case 'rejected':
      return 'rejected'
    case 'artifact':
      return 'artifact'
    default:
      return 'candidate'
  }
}

function mapDetectionWire(d: CandidateDetectionWire): CandidateDetection | null {
  const observationId = String(d.observationId ?? d.observation_id ?? '')
  const x = Number(d.x)
  const y = Number(d.y)
  if (!observationId || !Number.isFinite(x) || !Number.isFinite(y)) return null
  return {
    observationId,
    timestamp: String(d.timestamp ?? ''),
    ra: Number(d.ra ?? 0),
    dec: Number(d.dec ?? 0),
    x,
    y,
    snr: d.snr == null ? undefined : Number(d.snr),
  }
}

function numOrNaN(v: unknown): number {
  if (v == null || v === '') return Number.NaN
  const n = Number(v)
  return Number.isFinite(n) ? n : Number.NaN
}

/** Aplana pairs[] del backend al Candidate[] del UI. Nunca tira por datos rotos. */
export function mapCandidatesWire(wire: CandidateResponseWire | null | undefined): Candidate[] {
  const out: Candidate[] = []
  const seen = new Set<string>()
  try {
    for (const pair of wire?.pairs ?? []) {
      for (const c of pair?.candidatos ?? []) {
        const id = String(c?.candidate_id ?? '').trim()
        if (!id || seen.has(id)) continue
        seen.add(id)
        const motion = numOrNaN(c.motion_arcsec_yr)
        const displacement = numOrNaN(c.displacement_arcsec)
        const detections = (c.detections ?? [])
          .map(mapDetectionWire)
          .filter((d): d is CandidateDetection => d != null)
        out.push({
          id,
          ra: numOrNaN(c.ra),
          dec: numOrNaN(c.dec),
          detections,
          displacementArcsec: Number.isFinite(displacement)
            ? Math.abs(displacement)
            : Number.isFinite(motion)
              ? Math.abs(motion)
              : 0,
          motionArcsecPerYear: Number.isFinite(motion) ? motion : 0,
          snr: (() => {
            const s = numOrNaN(c.snr)
            return Number.isFinite(s) ? s : 0
          })(),
          status: mapCandidateStatus(c.status),
        })
      }
    }
  } catch (err) {
    console.warn('mapCandidatesWire: payload inválido, se ignora', err)
  }
  return out
}

export function mapImagesWire(wire: ImageListWire, absolutize: (url: string) => string): AnalysisImages {
  const firstShape = wire.imagenes.find((i) => Array.isArray(i.shape) && i.shape.length >= 2)?.shape
  const height = firstShape?.[0] ?? 0
  const width = firstShape?.[1] ?? 0

  return {
    width,
    height,
    pixelScaleArcsec: 6.2,
    epochs: (wire.imagenes ?? []).map((img) => ({
      observationId: img.obs_id,
      url: absolutize(img.preview_png_url),
    })),
    differences: [],
  }
}
