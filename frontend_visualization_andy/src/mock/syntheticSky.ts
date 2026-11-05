/**
 * Cielo sintético para la maqueta: genera épocas, imágenes de diferencia y
 * candidatos coherentes entre sí sin usar datos reales de SPHEREx.
 */
import type {
  AnalysisImages,
  Candidate,
  CandidateDetection,
  KnownObject,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'
import { pixelToSky } from '../lib/sky'
import {
  approximateBandwidth,
  detectorNumber,
  getSpectralBin,
  normalizeBands,
  partsFromBandIndex,
  primaryFromBands,
  SPECTRAL_FEATURES,
} from '../lib/spectral'
import type { FeatureLayerImage } from '../types/contracts'

const NPIX = 64
const PIXEL_SCALE_ARCSEC = 6.2
const PSF_SIGMA = 1.15
const NOISE_SIGMA = 1
const YEAR_MS = 365.25 * 24 * 3600 * 1000

const EPOCH_TIMESTAMPS = [
  '2025-05-10T17:04:37.741',
  '2025-05-24T21:52:33.088',
  '2025-12-06T12:32:03.461',
  '2025-12-11T17:55:08.684',
  '2026-05-17T10:53:45.256',
  '2026-06-06T08:19:42.195',
]

interface Mover {
  id: string
  x0: number
  y0: number
  /** px / año */
  vx: number
  vy: number
  flux: number
  snr: number
}

interface Star {
  x: number
  y: number
  flux: number
}

export interface SyntheticDataset {
  observations: ObservationSummary[]
  candidates: Candidate[]
  images: AnalysisImages
  knownObjects: KnownObject[]
}

function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function gaussian(rand: () => number) {
  const u = Math.max(rand(), 1e-12)
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand())
}

function seedFromRegion(q: RegionQuery) {
  const bands = normalizeBands(q.bands, q.bandpass, q.group)
  const bandsKey = bands.reduce((acc, b, i) => acc + b * (i + 1) * 13, 0)
  return (
    Math.floor(q.ra * 1000) * 31 +
    Math.floor((q.dec + 90) * 1000) * 17 +
    Math.floor(q.size * 1e4) +
    bandsKey +
    bands.length * 1009
  )
}

function addPsf(img: Float32Array, x: number, y: number, flux: number, sigma = PSF_SIGMA) {
  const r = Math.ceil(sigma * 4)
  const norm = flux / (2 * Math.PI * sigma * sigma)
  for (let j = Math.max(0, Math.floor(y - r)); j <= Math.min(NPIX - 1, Math.ceil(y + r)); j++) {
    for (let i = Math.max(0, Math.floor(x - r)); i <= Math.min(NPIX - 1, Math.ceil(x + r)); i++) {
      const dx = i - x
      const dy = j - y
      img[j * NPIX + i] += norm * Math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))
    }
  }
}

function addGalaxy(img: Float32Array, cx: number, cy: number, flux: number) {
  for (let j = 0; j < NPIX; j++) {
    for (let i = 0; i < NPIX; i++) {
      const dx = i - cx
      const dy = (j - cy) * 1.4
      const r = Math.sqrt(dx * dx + dy * dy)
      const theta = Math.atan2(dy, dx)
      const arms = 1 + 0.35 * Math.cos(2 * theta - r * 0.45)
      img[j * NPIX + i] += flux * Math.exp(-r / 6) * arms
    }
  }
}

/** Overlay RGBA de una feature IR (polvo / gases / H) para capas en el visor. */
function renderFeatureOverlay(
  weight: Float32Array,
  color: [number, number, number],
  opacityMax = 0.82,
): string {
  const canvas = document.createElement('canvas')
  canvas.width = NPIX
  canvas.height = NPIX
  const ctx = canvas.getContext('2d')!
  const out = ctx.createImageData(NPIX, NPIX)
  const hi = percentile(weight, 0.98) || 1
  const [cr, cg, cb] = color
  for (let k = 0; k < weight.length; k++) {
    const a = Math.min(1, Math.max(0, weight[k] / hi)) * opacityMax
    out.data[k * 4] = cr
    out.data[k * 4 + 1] = cg
    out.data[k * 4 + 2] = cb
    out.data[k * 4 + 3] = Math.round(255 * a)
  }
  ctx.putImageData(out, 0, 0)
  return canvas.toDataURL('image/png')
}

function buildFeatureLayers(rand: () => number, galaxy: { x: number; y: number }): FeatureLayerImage[] {
  return SPECTRAL_FEATURES.map((feat) => {
    const map = new Float32Array(NPIX * NPIX)
    if (feat.id === 'dust') {
      // Nube extendida alrededor de la galaxia sintética (bien visible).
      for (let j = 0; j < NPIX; j++) {
        for (let i = 0; i < NPIX; i++) {
          const dx = (i - galaxy.x) / 11
          const dy = (j - galaxy.y) / 8
          const r2 = dx * dx + dy * dy
          map[j * NPIX + i] = Math.exp(-r2) * (1.2 + 0.4 * Math.sin(i * 0.2 + j * 0.15))
        }
      }
    } else if (feat.id === 'gases') {
      // Filamentos curvos.
      for (let j = 0; j < NPIX; j++) {
        for (let i = 0; i < NPIX; i++) {
          const phase = Math.sin((i + j * 0.4) * 0.35) * 8
          const d = Math.abs(j - (NPIX * 0.45 + phase))
          map[j * NPIX + i] =
            1.4 * Math.exp(-(d * d) / 14) + 0.35 * Math.exp(-((i - NPIX * 0.7) ** 2) / 32)
        }
      }
    } else {
      // Hidrógeno: nudos compactos de emisión.
      const knots = [
        { x: 18 + rand() * 8, y: 22 + rand() * 8, s: 2.8 },
        { x: 40 + rand() * 10, y: 38 + rand() * 8, s: 2.4 },
        { x: 28 + rand() * 6, y: 48 + rand() * 6, s: 2.0 },
      ]
      for (const k of knots) {
        for (let j = 0; j < NPIX; j++) {
          for (let i = 0; i < NPIX; i++) {
            const dx = i - k.x
            const dy = j - k.y
            map[j * NPIX + i] += 1.5 * Math.exp(-(dx * dx + dy * dy) / (2 * k.s * k.s))
          }
        }
      }
    }
    return {
      id: feat.id,
      url: renderFeatureOverlay(map, feat.color),
      color: feat.color,
      bandpass: feat.bandpass,
      group: feat.group,
      wavelengthUm: feat.wavelengthUm,
    }
  })
}

const toSky = (q: RegionQuery, x: number, y: number) => pixelToSky(q, PIXEL_SCALE_ARCSEC, NPIX, NPIX, x, y)

function render(
  data: Float32Array,
  map: (v: number) => [number, number, number],
  invalid: [number, number, number],
): string {
  const canvas = document.createElement('canvas')
  canvas.width = NPIX
  canvas.height = NPIX
  const ctx = canvas.getContext('2d')!
  const out = ctx.createImageData(NPIX, NPIX)
  for (let k = 0; k < data.length; k++) {
    const v = data[k]
    const [r, g, b] = Number.isNaN(v) ? invalid : map(v)
    out.data[k * 4] = r
    out.data[k * 4 + 1] = g
    out.data[k * 4 + 2] = b
    out.data[k * 4 + 3] = 255
  }
  ctx.putImageData(out, 0, 0)
  return canvas.toDataURL('image/png')
}

function percentile(values: Float32Array, p: number) {
  const finite = Array.from(values).filter((v) => !Number.isNaN(v))
  finite.sort((a, b) => a - b)
  return finite[Math.min(finite.length - 1, Math.floor(p * finite.length))]
}

export function generateSyntheticDataset(q: RegionQuery): SyntheticDataset {
  const rand = mulberry32(seedFromRegion(q))
  const t0 = Date.parse(`${EPOCH_TIMESTAMPS[0]}Z`)
  const years = EPOCH_TIMESTAMPS.map((t) => (Date.parse(`${t}Z`) - t0) / YEAR_MS)

  const stars: Star[] = Array.from({ length: 55 }, () => ({
    x: rand() * NPIX,
    y: rand() * NPIX,
    flux: 25 * Math.pow(rand(), -0.9),
  }))
  const galaxy = { x: NPIX * (0.35 + rand() * 0.3), y: NPIX * (0.35 + rand() * 0.3), flux: 6 + rand() * 4 }

  const movers: Mover[] = [
    { id: 'C-001', x0: 10 + rand() * 6, y0: 14 + rand() * 6, vx: 26, vy: 16, flux: 120, snr: 18.4 },
    { id: 'C-002', x0: 50 - rand() * 6, y0: 48 + rand() * 4, vx: -11, vy: -9, flux: 55, snr: 7.9 },
  ]
  const artifact = { epoch: 2, x: 40 + rand() * 8, y: 20 + rand() * 6 }

  const epochs: Float32Array[] = years.map((yr, e) => {
    const img = new Float32Array(NPIX * NPIX)
    const bg = 8 + rand() * 1.5
    for (let k = 0; k < img.length; k++) {
      const j = Math.floor(k / NPIX)
      img[k] = bg + 0.02 * j + gaussian(rand) * NOISE_SIGMA
    }
    addGalaxy(img, galaxy.x, galaxy.y, galaxy.flux)
    for (const s of stars) addPsf(img, s.x, s.y, s.flux)
    for (const m of movers) addPsf(img, m.x0 + m.vx * yr, m.y0 + m.vy * yr, m.flux)
    if (e === artifact.epoch) addPsf(img, artifact.x, artifact.y, 90, 0.45)
    const nInvalid = 1 + Math.floor(rand() * 4)
    for (let n = 0; n < nInvalid; n++) img[Math.floor(rand() * img.length)] = Number.NaN
    return img
  })

  const lo = percentile(epochs[0], 0.02)
  const hi = percentile(epochs[0], 0.995)
  const stretch = (v: number): [number, number, number] => {
    const n = Math.min(1, Math.max(0, (v - lo) / (hi - lo)))
    const s = Math.asinh(n * 10) / Math.asinh(10)
    return [Math.round(255 * Math.pow(s, 1.05)), Math.round(255 * s), Math.round(255 * Math.min(1, s * 1.08 + 0.03))]
  }
  const diffLimit = 6 * NOISE_SIGMA * Math.SQRT2
  const diverging = (v: number): [number, number, number] => {
    const n = Math.max(-1, Math.min(1, v / diffLimit))
    const a = Math.pow(Math.abs(n), 0.7)
    return n >= 0
      ? [Math.round(12 + 243 * a), Math.round(12 + 150 * a), Math.round(18 + 30 * a)]
      : [Math.round(12 + 30 * a), Math.round(12 + 190 * a), Math.round(18 + 237 * a)]
  }

  const bands = normalizeBands(q.bands, q.bandpass, q.group)
  const primary = primaryFromBands(bands)
  const bandpass = primary.bandpass
  const group = primary.group
  const bin = getSpectralBin(bandpass, group)
  const selectedBins = bands.map((i) => partsFromBandIndex(i))
  const wlMin = Math.min(...selectedBins.map((b) => b.wlMin))
  const wlMax = Math.max(...selectedBins.map((b) => b.wlMax))
  const wlCenter =
    selectedBins.reduce((acc, b) => acc + b.wlCenter, 0) / selectedBins.length
  const bandwidth =
    bands.length > 1 ? +(wlMax - wlMin).toFixed(6) : approximateBandwidth(bandpass)
  const detector = detectorNumber(bandpass)

  const observations: ObservationSummary[] = EPOCH_TIMESTAMPS.map((timestamp, e) => ({
    id: `MOCK-${String(e + 1).padStart(3, '0')}`,
    timestamp,
    ra: q.ra,
    dec: q.dec,
    detector,
    wavelength: bands.length > 1 ? wlCenter : bin.wlCenter + (rand() - 0.5) * bandwidth * 0.08,
    bandwidth,
    wavelength_source: 'WCS-WAVE',
    bandwidth_source: 'WCS-WAVE',
    spectral_calibration_source: 'WCS-WAVE',
    spectral_calibration_quality: 'approximate',
    spectral_unit: 'μm',
    fits_source: `mock://spherex/${q.qr ?? 'qr2'}/${bandpass}/g${String(group).padStart(2, '0')}/epoch_${String(e + 1).padStart(3, '0')}.fits`,
    shape: [NPIX, NPIX],
    n_invalid_pixels: epochs[e].reduce((acc, v) => acc + (Number.isNaN(v) ? 1 : 0), 0),
    metadata: {
      qr: q.qr ?? 'qr2',
      bandpass,
      group,
      bands,
      bandCount: bands.length,
      source: 'mock',
    },
  }))

  const refIndex = 0
  const images: AnalysisImages = {
    width: NPIX,
    height: NPIX,
    pixelScaleArcsec: PIXEL_SCALE_ARCSEC,
    epochs: epochs.map((img, e) => ({ observationId: observations[e].id, url: render(img, stretch, [90, 20, 45]) })),
    differences: epochs
      .map((img, e) => ({ img, e }))
      .filter(({ e }) => e !== refIndex)
      .map(({ img, e }) => {
        const ref = epochs[refIndex]
        const diff = img.map((v, k) => v - ref[k])
        return {
          observationId: observations[e].id,
          referenceId: observations[refIndex].id,
          url: render(diff, diverging, [70, 70, 70]),
        }
      }),
    featureLayers: buildFeatureLayers(rand, galaxy),
  }

  const candidates: Candidate[] = movers.map((m) => {
    const detections: CandidateDetection[] = years.map((yr, e) => {
      const x = m.x0 + m.vx * yr
      const y = m.y0 + m.vy * yr
      return {
        observationId: observations[e].id,
        timestamp: observations[e].timestamp,
        x,
        y,
        ...toSky(q, x, y),
        snr: +(m.snr * (0.85 + rand() * 0.3)).toFixed(1),
      }
    })
    const first = detections[0]
    const last = detections[detections.length - 1]
    const displacementArcsec = Math.hypot(last.x - first.x, last.y - first.y) * PIXEL_SCALE_ARCSEC
    const mid = detections[Math.floor(detections.length / 2)]
    return {
      id: m.id,
      ra: mid.ra,
      dec: mid.dec,
      detections,
      displacementArcsec,
      motionArcsecPerYear: displacementArcsec / years[years.length - 1],
      snr: m.snr,
      status: 'candidate',
    }
  })

  const artSky = toSky(q, artifact.x, artifact.y)
  candidates.push({
    id: 'C-003',
    ...artSky,
    detections: [
      {
        observationId: observations[artifact.epoch].id,
        timestamp: observations[artifact.epoch].timestamp,
        x: artifact.x,
        y: artifact.y,
        ...artSky,
        snr: 9.2,
      },
    ],
    displacementArcsec: 0,
    motionArcsecPerYear: 0,
    snr: 9.2,
    status: 'artifact',
  })

  const knownObjects: KnownObject[] = [
    {
      name: '2025 QX17 (simulated)',
      type: 'asteroid',
      magnitude: 17.8,
      positions: candidates[0].detections.map((d) => ({
        observationId: d.observationId,
        ra: d.ra,
        dec: d.dec,
        x: d.x + (rand() - 0.5) * 0.6,
        y: d.y + (rand() - 0.5) * 0.6,
      })),
    },
  ]

  return { observations, candidates, images, knownObjects }
}
