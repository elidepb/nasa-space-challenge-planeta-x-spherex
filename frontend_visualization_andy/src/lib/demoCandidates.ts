/**
 * TEMP VIDEO DEMO — borrar este archivo y su uso en `useAnalysis` cuando Etner
 * devuelva candidatos reales.
 *
 * Marca manchas blancas notorias del PNG. Sustituye candidatos del API.
 */
import { pixelToSky } from './sky'
import type {
  AnalysisImages,
  Candidate,
  CandidateDetection,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'

export const USE_DEMO_CANDIDATES = false

type Peak = { x: number; y: number; v: number }
type Frame = { observationId: string; timestamp: string; url: string }

function gridSize(images: AnalysisImages, observations: ObservationSummary[]) {
  const fromObs = observations.find((o) => Array.isArray(o.shape) && o.shape.length >= 2)?.shape
  const w = images.width > 0 ? images.width : Number(fromObs?.[1]) || 64
  const h = images.height > 0 ? images.height : Number(fromObs?.[0]) || 64
  const ps = images.pixelScaleArcsec > 0 ? images.pixelScaleArcsec : 6.2
  return { w: Math.max(8, Math.round(w)), h: Math.max(8, Math.round(h)), ps }
}

function loadImg(src: string, crossOrigin?: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    if (crossOrigin) img.crossOrigin = crossOrigin
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`demoCandidates: load fail ${src.slice(0, 80)}`))
    img.src = src
  })
}

/** En dev, reescribe localhost:8000 → /api-proxy (vite) para canvas same-origin. */
function readableUrl(url: string): string {
  if (typeof window === 'undefined') return url
  try {
    const u = new URL(url, window.location.href)
    if (u.origin === window.location.origin) return url
    if (u.hostname === 'localhost' || u.hostname === '127.0.0.1') {
      return `/api-proxy${u.pathname}${u.search}`
    }
  } catch {
    // URL relativa
  }
  return url
}

/**
 * Carga píxeles legibles en canvas. fetch→blob evita CORS tainted
 * (el <img> del visor puede verse igual aunque el canvas falle).
 */
async function sampleLuma(url: string, w: number, h: number): Promise<Float32Array | null> {
  let objectUrl: string | null = null
  try {
    let img: HTMLImageElement | null = null
    const candidates = [readableUrl(url), url]
    for (const src of candidates) {
      try {
        const res = await fetch(src, { mode: 'cors', credentials: 'omit' })
        if (res.ok) {
          objectUrl = URL.createObjectURL(await res.blob())
          img = await loadImg(objectUrl)
          break
        }
      } catch {
        // prueba siguiente
      }
    }
    if (!img) {
      try {
        img = await loadImg(url, 'anonymous')
      } catch {
        img = await loadImg(url)
      }
    }

    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return null
    ctx.drawImage(img, 0, 0, w, h)
    const { data } = ctx.getImageData(0, 0, w, h)
    const luma = new Float32Array(w * h)
    let max = 0
    for (let i = 0, p = 0; i < data.length; i += 4, p++) {
      const v = 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]
      luma[p] = v
      if (v > max) max = v
    }
    // Canvas vacío / tainted → todo 0
    if (max < 1) return null
    return luma
  } catch {
    return null
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl)
  }
}

function boxBlur3(src: Float32Array, w: number, h: number): Float32Array {
  const out = new Float32Array(w * h)
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      let s = 0
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) s += src[(y + dy) * w + (x + dx)]
      }
      out[y * w + x] = s / 9
    }
  }
  return out
}

function percentile(values: Float32Array, p: number) {
  const a = Array.from(values)
  a.sort((x, y) => x - y)
  const i = Math.min(a.length - 1, Math.max(0, Math.floor((p / 100) * (a.length - 1))))
  return a[i]
}

function apertureMean(luma: Float32Array, w: number, h: number, cx: number, cy: number, r: number) {
  const x0 = Math.max(0, Math.floor(cx - r))
  const x1 = Math.min(w - 1, Math.ceil(cx + r))
  const y0 = Math.max(0, Math.floor(cy - r))
  const y1 = Math.min(h - 1, Math.ceil(cy + r))
  const r2 = r * r
  let s = 0
  let n = 0
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x + 0.5 - cx
      const dy = y + 0.5 - cy
      if (dx * dx + dy * dy <= r2) {
        s += luma[y * w + x]
        n++
      }
    }
  }
  return n > 0 ? s / n : 0
}

function centroid(luma: Float32Array, w: number, h: number, cx: number, cy: number, r: number): Peak {
  const x0 = Math.max(0, Math.floor(cx - r))
  const x1 = Math.min(w - 1, Math.ceil(cx + r))
  const y0 = Math.max(0, Math.floor(cy - r))
  const y1 = Math.min(h - 1, Math.ceil(cy + r))
  const r2 = r * r
  let sx = 0
  let sy = 0
  let sw = 0
  let peak = 0
  const floor = percentile(luma, 40)
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x + 0.5 - cx
      const dy = y + 0.5 - cy
      if (dx * dx + dy * dy > r2) continue
      const raw = luma[y * w + x]
      const v = Math.max(0, raw - floor)
      sx += (x + 0.5) * v
      sy += (y + 0.5) * v
      sw += v
      if (raw > peak) peak = raw
    }
  }
  if (sw <= 0) return { x: cx, y: cy, v: peak }
  return { x: sx / sw, y: sy / sw, v: peak }
}

/** Manchas brillantes: suavizado + umbral relativo + máximo local. */
function findBrightBlobs(luma: Float32Array, w: number, h: number, maxPeaks: number): Peak[] {
  const smooth = boxBlur3(luma, w, h)
  const p50 = percentile(smooth, 50)
  const p99 = percentile(smooth, 99)
  const p995 = percentile(smooth, 99.5)
  // Umbral adaptable al contraste del cutout (ruido SPHEREx vs estrellas).
  const thr = Math.max(p50 + (p99 - p50) * 0.55, p995 * 0.7, p50 + 15)
  const margin = Math.max(2, Math.floor(Math.min(w, h) * 0.04))
  const minDist = Math.max(3, Math.floor(Math.min(w, h) * 0.06))
  const neigh = Math.max(1, Math.floor(Math.min(w, h) * 0.012))
  const rAper = Math.max(1.2, Math.min(w, h) * 0.018)

  const scored: Peak[] = []
  for (let y = margin; y < h - margin; y++) {
    for (let x = margin; x < w - margin; x++) {
      const i = y * w + x
      const v = smooth[i]
      if (v < thr) continue
      let isMax = true
      for (let dy = -neigh; dy <= neigh && isMax; dy++) {
        for (let dx = -neigh; dx <= neigh; dx++) {
          if (dx === 0 && dy === 0) continue
          if (smooth[(y + dy) * w + (x + dx)] > v) {
            isMax = false
            break
          }
        }
      }
      if (!isMax) continue
      const flux = apertureMean(luma, w, h, x + 0.5, y + 0.5, rAper)
      if (flux < thr * 0.75) continue
      scored.push({ x: x + 0.5, y: y + 0.5, v: flux })
    }
  }

  scored.sort((a, b) => b.v - a.v)
  const picked: Peak[] = []
  for (const p of scored) {
    if (picked.some((q) => Math.hypot(q.x - p.x, q.y - p.y) < minDist)) continue
    picked.push(centroid(luma, w, h, p.x, p.y, rAper * 1.8))
    if (picked.length >= maxPeaks) break
  }

  // Fallback: si el umbral fue demasiado alto, toma los máximos más brillantes del smooth.
  if (picked.length === 0) {
    const looseThr = Math.max(p99 * 0.85, p50 + 8)
    const loose: Peak[] = []
    for (let y = margin; y < h - margin; y++) {
      for (let x = margin; x < w - margin; x++) {
        const i = y * w + x
        const v = smooth[i]
        if (v < looseThr) continue
        if (v >= smooth[i - 1] && v >= smooth[i + 1] && v >= smooth[i - w] && v >= smooth[i + w]) {
          loose.push({ x: x + 0.5, y: y + 0.5, v })
        }
      }
    }
    loose.sort((a, b) => b.v - a.v)
    for (const p of loose) {
      if (picked.some((q) => Math.hypot(q.x - p.x, q.y - p.y) < minDist)) continue
      picked.push(centroid(luma, w, h, p.x, p.y, rAper * 1.8))
      if (picked.length >= maxPeaks) break
    }
  }

  return picked
}

/** Empareja por cercanía + brillo parecido (las manchas grandes deben seguir siendo grandes). */
function nearestUnused(
  peaks: Peak[],
  x: number,
  y: number,
  maxDist: number,
  used: Set<number>,
  refFlux?: number,
) {
  let best: { peak: Peak; idx: number; score: number } | null = null
  for (let i = 0; i < peaks.length; i++) {
    if (used.has(i)) continue
    const d = Math.hypot(peaks[i].x - x, peaks[i].y - y)
    if (d > maxDist) continue
    const fluxRatio =
      refFlux && refFlux > 0 ? Math.min(peaks[i].v, refFlux) / Math.max(peaks[i].v, refFlux) : 1
    // Penaliza si el tamaño/brillo cambia mucho; premia cercanía.
    const score = d / Math.max(maxDist, 1) + (1 - fluxRatio) * 1.5
    if (!best || score < best.score) best = { peak: peaks[i], idx: i, score }
  }
  return best
}

/** Misma “categoría” de brillo aunque se haya movido el cutout. */
function bestFluxMatch(peaks: Peak[], refFlux: number, used: Set<number>) {
  let best: { peak: Peak; idx: number; score: number } | null = null
  for (let i = 0; i < peaks.length; i++) {
    if (used.has(i)) continue
    const ratio = Math.min(peaks[i].v, refFlux) / Math.max(peaks[i].v, refFlux, 1)
    const score = 1 - ratio
    if (!best || score < best.score) best = { peak: peaks[i], idx: i, score }
  }
  return best && best.score < 0.55 ? best : null
}

function pairedEpochs(observations: ObservationSummary[], images: AnalysisImages): Frame[] {
  const n = Math.min(observations.length, images.epochs.length)
  if (n < 1) return []
  const byId = new Map(images.epochs.map((e) => [e.observationId, e.url]))
  const out: Frame[] = []
  for (let i = 0; i < n; i++) {
    const obs = observations[i]
    const url = byId.get(obs.id) ?? images.epochs[i]?.url
    if (!url) continue
    out.push({ observationId: obs.id, timestamp: obs.timestamp ?? '', url })
  }
  return out
}

function toCandidate(
  chain: Peak[],
  frames: Frame[],
  index: number,
  region: RegionQuery,
  w: number,
  h: number,
  ps: number,
): Candidate {
  const dets: CandidateDetection[] = chain.map((p, e) => {
    const sky = pixelToSky(region, ps, w, h, p.x, p.y)
    return {
      observationId: frames[Math.min(e, frames.length - 1)].observationId,
      timestamp: frames[Math.min(e, frames.length - 1)].timestamp,
      ra: sky.ra,
      dec: sky.dec,
      x: p.x,
      y: p.y,
      snr: +(12 + p.v / 20).toFixed(1),
    }
  })
  // Si la cadena es más corta (fallback fijo), replica la posición en todas las épocas.
  while (dets.length < frames.length) {
    const src = dets[0]
    const fr = frames[dets.length]
    dets.push({ ...src, observationId: fr.observationId, timestamp: fr.timestamp })
  }
  const first = dets[0]
  const last = dets[dets.length - 1]
  const mid = dets[Math.floor(dets.length / 2)]
  const displacementArcsec = Math.hypot(last.x - first.x, last.y - first.y) * ps
  const years =
    first.timestamp && last.timestamp
      ? Math.max(0.05, (Date.parse(last.timestamp) - Date.parse(first.timestamp)) / (365.25 * 864e5))
      : 1
  return {
    id: `C-${String(index + 1).padStart(3, '0')}`,
    ra: mid.ra,
    dec: mid.dec,
    detections: dets,
    displacementArcsec: +displacementArcsec.toFixed(2),
    motionArcsecPerYear: +(displacementArcsec / years).toFixed(2),
    snr: last.snr ?? 12,
    status: 'candidate',
  }
}

export async function fillDemoCandidatesIfEmpty(
  candidates: Candidate[],
  observations: ObservationSummary[],
  images: AnalysisImages,
  region: RegionQuery,
): Promise<Candidate[]> {
  if (!USE_DEMO_CANDIDATES) return candidates

  const frames = pairedEpochs(observations, images)
  if (frames.length < 1) return []

  const { w, h, ps } = gridSize(images, observations)
  const long = Math.max(w, h)
  const workLong = Math.min(384, Math.max(long, 96))
  const workW = Math.max(32, Math.round((w / long) * workLong))
  const workH = Math.max(32, Math.round((h / long) * workLong))
  const scaleX = w / workW
  const scaleY = h / workH
  // Los cutouts entre visitas no están perfectamente alineados: tolerancia amplia.
  const maxStep = Math.max(8, Math.min(w, h) * 0.22)

  const peaksPerEpoch: Peak[][] = []
  for (const fr of frames) {
    const luma = await sampleLuma(fr.url, workW, workH)
    if (!luma) {
      console.warn('demoCandidates: no se pudieron leer píxeles de', fr.url)
      peaksPerEpoch.push([])
      continue
    }
    peaksPerEpoch.push(
      findBrightBlobs(luma, workW, workH, 24).map((p) => ({
        x: p.x * scaleX,
        y: p.y * scaleY,
        v: p.v,
      })),
    )
  }

  const baseIdx = peaksPerEpoch.findIndex((p) => p.length > 0)
  const base = baseIdx >= 0 ? peaksPerEpoch[baseIdx] : []
  if (base.length === 0) {
    console.warn('demoCandidates: sin manchas detectadas')
    return []
  }

  // Ordenar por brillo (las “obvias” primero). peaks ya vienen ordenados, refuerzo.
  for (const peaks of peaksPerEpoch) peaks.sort((a, b) => b.v - a.v)

  const out: Candidate[] = []
  const usedPerEpoch = peaksPerEpoch.map(() => new Set<number>())
  const target = 5

  // 1) Prioridad: manchas grandes/brillantes. Match por posición O por brillo similar.
  for (let s = 0; s < base.length && out.length < target; s++) {
    if (usedPerEpoch[baseIdx].has(s)) continue
    const seed = base[s]
    const chain: Peak[] = new Array(frames.length)
    chain[baseIdx] = seed
    usedPerEpoch[baseIdx].add(s)

    let ok = true
    for (let e = 0; e < frames.length; e++) {
      if (e === baseIdx) continue
      if (peaksPerEpoch[e].length === 0) {
        ok = false
        break
      }
      const byPos = nearestUnused(peaksPerEpoch[e], seed.x, seed.y, maxStep, usedPerEpoch[e], seed.v)
      const hit = byPos ?? bestFluxMatch(peaksPerEpoch[e], seed.v, usedPerEpoch[e])
      if (!hit) {
        // Fuente muy brillante: márcala igual en esta época con la posición de la semilla
        // (mejor círculo en la estrella grande que perderla por un shift del cutout).
        if (s < 3) {
          chain[e] = seed
          continue
        }
        ok = false
        break
      }
      usedPerEpoch[e].add(hit.idx)
      chain[e] = hit.peak
    }
    if (!ok || chain.some((p) => !p)) {
      usedPerEpoch[baseIdx].delete(s)
      continue
    }
    out.push(toCandidate(chain as Peak[], frames, out.length, region, w, h, ps))
  }

  // 2) Relleno: brillantes de la época base aún libres (fijas).
  for (let s = 0; s < base.length && out.length < target; s++) {
    if (usedPerEpoch[baseIdx].has(s)) continue
    const p = base[s]
    usedPerEpoch[baseIdx].add(s)
    out.push(toCandidate(
      frames.map(() => p),
      frames,
      out.length,
      region,
      w,
      h,
      ps,
    ))
  }

  return out
}
