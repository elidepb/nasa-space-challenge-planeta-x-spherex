import type { ObservationSummary, RegionQuery } from '../types/contracts'
import { pixelToSky, timestampMs } from './sky'

export interface HunterMark {
  observationId: string
  x: number
  y: number
}

export interface TrackPoint {
  observationId: string
  x: number
  y: number
}

const YEAR_MS = 365.25 * 24 * 3600 * 1000
const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const
export type CompassPoint = (typeof COMPASS)[number]

export function sortMarks(marks: HunterMark[], observations: ObservationSummary[]) {
  const order = new Map(observations.map((o, i) => [o.id, i]))
  return [...marks].sort((a, b) => (order.get(a.observationId) ?? 0) - (order.get(b.observationId) ?? 0))
}

export interface MotionResult {
  displacementArcsec: number
  motionArcsecPerYear: number
  /** Ángulo de posición: 0° = Norte, 90° = Este. */
  positionAngleDeg: number
  direction: CompassPoint
  spanDays: number
  start: { ra: number; dec: number }
  end: { ra: number; dec: number }
}

/** Norte arriba y Este a la izquierda, como en `pixelToSky`. */
export function computeMotion(
  marks: HunterMark[],
  observations: ObservationSummary[],
  region: Pick<RegionQuery, 'ra' | 'dec'>,
  pixelScaleArcsec: number,
  width: number,
  height: number,
): MotionResult | null {
  const sorted = sortMarks(marks, observations)
  if (sorted.length < 2) return null
  const first = sorted[0]
  const last = sorted[sorted.length - 1]
  const t = (id: string) => timestampMs(observations.find((o) => o.id === id)?.timestamp ?? '')
  const spanMs = t(last.observationId) - t(first.observationId)
  const dx = last.x - first.x
  const dy = last.y - first.y
  const displacementArcsec = Math.hypot(dx, dy) * pixelScaleArcsec
  const pa = ((Math.atan2(-dx, -dy) * 180) / Math.PI + 360) % 360
  return {
    displacementArcsec,
    motionArcsecPerYear: spanMs > 0 ? displacementArcsec / (spanMs / YEAR_MS) : 0,
    positionAngleDeg: pa,
    direction: COMPASS[Math.round(pa / 45) % 8],
    spanDays: spanMs / 86_400_000,
    start: pixelToSky(region, pixelScaleArcsec, width, height, first.x, first.y),
    end: pixelToSky(region, pixelScaleArcsec, width, height, last.x, last.y),
  }
}

/** Distancia media (px) entre las marcas y una trayectoria en las épocas comunes. */
export function matchTrack(marks: HunterMark[], track: TrackPoint[], tolerancePx: number) {
  const byObs = new Map(track.map((p) => [p.observationId, p]))
  const dists = marks.flatMap((m) => {
    const p = byObs.get(m.observationId)
    return p ? [Math.hypot(p.x - m.x, p.y - m.y)] : []
  })
  if (dists.length < 2) return null
  const mean = dists.reduce((a, b) => a + b, 0) / dists.length
  return mean <= tolerancePx ? { meanPx: mean, common: dists.length } : null
}

export function bestMatch<T>(marks: HunterMark[], items: T[], track: (item: T) => TrackPoint[], tolerancePx: number) {
  let best: { item: T; meanPx: number; common: number } | null = null
  for (const item of items) {
    const m = matchTrack(marks, track(item), tolerancePx)
    if (m && (!best || m.meanPx < best.meanPx)) best = { item, ...m }
  }
  return best
}

export const simbadUrl = (ra: number, dec: number, radiusArcsec = 30) =>
  `https://simbad.cds.unistra.fr/simbad/sim-coo?Coord=${ra.toFixed(6)}+${dec >= 0 ? '%2B' : ''}${dec.toFixed(6)}&Radius=${radiusArcsec}&Radius.unit=arcsec`

export const sbdbUrl = (name: string) =>
  `https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=${encodeURIComponent(name.replace(/\s*\(.*\)$/, ''))}`
