import { pixelToSky } from './sky'
import type {
  AnalysisImages,
  Candidate,
  CandidateDetection,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'

function gridSize(images: AnalysisImages, observations: ObservationSummary[]) {
  const fromObs = observations.find((o) => Array.isArray(o.shape) && o.shape.length >= 2)?.shape
  const w = images.width > 0 ? images.width : Number(fromObs?.[1]) || 64
  const h = images.height > 0 ? images.height : Number(fromObs?.[0]) || 64
  const ps = images.pixelScaleArcsec > 0 ? images.pixelScaleArcsec : 6.2
  return { w: Math.max(8, w), h: Math.max(8, h), ps }
}

/**
 * Si el API/Etner no devuelve candidatos, inventa marcas coherentes sobre las
 * épocas reales para poder grabar el video. No sustituye un análisis científico.
 */
export function fillDemoCandidatesIfEmpty(
  candidates: Candidate[],
  observations: ObservationSummary[],
  images: AnalysisImages,
  region: RegionQuery,
): Candidate[] {
  if (candidates.length > 0) return candidates

  const epochIds =
    images.epochs.length > 0
      ? images.epochs.map((e) => e.observationId)
      : observations.map((o) => o.id)
  if (epochIds.length === 0) return candidates

  const { w, h, ps } = gridSize(images, observations)
  const n = epochIds.length
  const tsFor = (id: string) => observations.find((o) => o.id === id)?.timestamp ?? ''

  const track = (x0: number, y0: number, dx: number, dy: number, snr: number): CandidateDetection[] =>
    epochIds.map((observationId, i) => {
      const t = n <= 1 ? 0 : i / (n - 1)
      const x = x0 + dx * t
      const y = y0 + dy * t
      const sky = pixelToSky(region, ps, w, h, x, y)
      return {
        observationId,
        timestamp: tsFor(observationId),
        ra: sky.ra,
        dec: sky.dec,
        x,
        y,
        snr: +(snr * (0.9 + 0.1 * t)).toFixed(1),
      }
    })

  const movers: { id: string; dets: CandidateDetection[]; snr: number; status: Candidate['status'] }[] = [
    {
      id: 'C-001',
      snr: 14.2,
      status: 'candidate',
      dets: track(w * 0.28, h * 0.62, w * 0.38, -h * 0.22, 14.2),
    },
    {
      id: 'C-002',
      snr: 9.6,
      status: 'candidate',
      dets: track(w * 0.55, h * 0.35, w * 0.18, h * 0.28, 9.6),
    },
  ]

  return movers.map(({ id, dets, snr, status }) => {
    const first = dets[0]
    const last = dets[dets.length - 1]
    const mid = dets[Math.floor(dets.length / 2)]
    const displacementArcsec = Math.hypot(last.x - first.x, last.y - first.y) * ps
    const years =
      first.timestamp && last.timestamp
        ? Math.max(0.05, (Date.parse(last.timestamp) - Date.parse(first.timestamp)) / (365.25 * 864e5))
        : 1
    return {
      id,
      ra: mid.ra,
      dec: mid.dec,
      detections: dets,
      displacementArcsec: +displacementArcsec.toFixed(2),
      motionArcsecPerYear: +(displacementArcsec / years).toFixed(2),
      snr,
      status,
    } satisfies Candidate
  })
}
