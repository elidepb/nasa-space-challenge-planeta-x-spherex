import type { RegionQuery } from '../types/contracts'

/** Proyección tangente simplificada: válida para cutouts pequeños como los de SPHEREx. */
export function pixelToSky(
  region: Pick<RegionQuery, 'ra' | 'dec'>,
  pixelScaleArcsec: number,
  width: number,
  height: number,
  x: number,
  y: number,
) {
  const cx = (width - 1) / 2
  const cy = (height - 1) / 2
  const dec = region.dec + ((cy - y) * pixelScaleArcsec) / 3600
  const ra = region.ra + ((cx - x) * pixelScaleArcsec) / 3600 / Math.cos((region.dec * Math.PI) / 180)
  return { ra: (ra + 360) % 360, dec }
}

export function formatRaHms(raDeg: number) {
  const [hh, mm, ss] = sexagesimal(raDeg / 15, 2)
  return `${String(hh).padStart(2, '0')}h ${String(mm).padStart(2, '0')}m ${ss.toFixed(2).padStart(5, '0')}s`
}

export function formatDecDms(decDeg: number) {
  const sign = decDeg < 0 ? '−' : '+'
  const [dd, mm, ss] = sexagesimal(Math.abs(decDeg), 1)
  return `${sign}${String(dd).padStart(2, '0')}° ${String(mm).padStart(2, '0')}′ ${ss.toFixed(1).padStart(4, '0')}″`
}

/** Redondea antes de descomponer para no producir "60.0″". */
function sexagesimal(value: number, decimals: number): [number, number, number] {
  const f = 10 ** decimals
  const total = Math.round(value * 3600 * f)
  const whole = Math.floor(total / (3600 * f))
  const rest = total - whole * 3600 * f
  const min = Math.floor(rest / (60 * f))
  return [whole, min, (rest - min * 60 * f) / f]
}

export function formatTimestamp(ts: string) {
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? ts : `${ts}Z`)
  if (Number.isNaN(d.getTime())) return ts
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
}

export function timestampMs(ts: string) {
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? ts : `${ts}Z`)
}
