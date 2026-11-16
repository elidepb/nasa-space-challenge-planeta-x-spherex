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

// ============================================================================
// Consultas Directas desde el Navegador (CORS Habilitado) para Catálogos Vivos
// ============================================================================

export interface KnownCatalogObject {
  source: 'GAIA_DR3' | 'SKYBOT_ASTEROID' | 'NEOSSAT_CADC'
  id: string
  ra: number
  dec: number
  pmra?: number // mas/yr
  pmdec?: number // mas/yr
  g_mag?: number
  velocity_arcsec_hr?: number
  infoUrl: string
}

/**
 * Consulta catálogos vivos (Gaia DR3 y SkyBoT) a través del backend FastAPI
 * con CORS habilitado, garantizando que el navegador no reciba bloqueos de origen cruzado.
 */
export async function fetchCrossmatchCatalogs(
  ra: number,
  dec: number,
  radiusArcsec: number = 180,
  mjd: number = 60400,
): Promise<KnownCatalogObject[]> {
  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  try {
    const res = await fetch(
      `${apiUrl}/api/v1/crossmatch?ra=${ra}&dec=${dec}&radius=${radiusArcsec}&mjd=${mjd}`,
    )
    if (!res.ok) return []
    return (await res.json()) as KnownCatalogObject[]
  } catch {
    return []
  }
}

/**
 * 1. Consulta Gaia DR3 en vivo (a través del backend sin restricciones CORS)
 *    para encontrar estrellas con alto movimiento propio en el recorte actual.
 */
export async function fetchGaiaHighPMStars(
  ra: number,
  dec: number,
  radiusArcsec: number = 120,
): Promise<KnownCatalogObject[]> {
  const all = await fetchCrossmatchCatalogs(ra, dec, radiusArcsec)
  return all.filter((o) => o.source === 'GAIA_DR3')
}

/**
 * 2. Consulta SkyBoT (IMCCE ssp.imcce.fr) para identificar asteroides en esa fecha y coordenada.
 */
export async function fetchKnownAsteroidsSkyBoT(
  ra: number,
  dec: number,
  mjd: number,
  radiusArcsec: number = 180,
): Promise<KnownCatalogObject[]> {
  const all = await fetchCrossmatchCatalogs(ra, dec, radiusArcsec, mjd)
  return all.filter((o) => o.source === 'SKYBOT_ASTEROID')
}

/**
 * 3. Consulta el telescopio espacial NEOSSat.
 */
export async function fetchNEOSSatObservations(
  ra: number,
  dec: number,
  radiusArcsec: number = 300,
): Promise<KnownCatalogObject[]> {
  const all = await fetchCrossmatchCatalogs(ra, dec, radiusArcsec)
  return all.filter((o) => o.source === 'NEOSSAT_CADC')
}
