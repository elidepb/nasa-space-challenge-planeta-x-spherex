/**
 * Ajustes de visualización aplicados en el navegador sobre los PNG que entrega
 * el backend. Las imágenes de otros orígenes necesitan cabeceras CORS para
 * poder leerse desde un canvas.
 */

export type Stretch = 'linear' | 'sqrt' | 'log' | 'asinh'
export type Colormap = 'gray' | 'inferno' | 'viridis' | 'cividis'

export interface ImageSettings {
  stretch: Stretch
  colormap: Colormap
  /** -0.5 .. 0.5 */
  brightness: number
  /** 0.5 .. 3 */
  contrast: number
  invert: boolean
}

export const DEFAULT_IMAGE_SETTINGS: ImageSettings = {
  stretch: 'linear',
  colormap: 'gray',
  brightness: 0,
  contrast: 1,
  invert: false,
}

export const STRETCHES: Stretch[] = ['linear', 'sqrt', 'log', 'asinh']
export const COLORMAPS: Colormap[] = ['gray', 'inferno', 'viridis', 'cividis']

type RGB = [number, number, number]

const COLORMAP_STOPS: Record<Colormap, RGB[]> = {
  gray: [
    [0, 0, 0],
    [255, 255, 255],
  ],
  inferno: [
    [0, 0, 4],
    [40, 11, 84],
    [101, 21, 110],
    [159, 42, 99],
    [212, 72, 66],
    [245, 125, 21],
    [250, 193, 39],
    [252, 255, 164],
  ],
  viridis: [
    [68, 1, 84],
    [72, 40, 120],
    [62, 74, 137],
    [49, 104, 142],
    [38, 130, 142],
    [31, 158, 137],
    [53, 183, 121],
    [109, 205, 89],
    [180, 222, 44],
    [253, 231, 37],
  ],
  cividis: [
    [0, 34, 78],
    [35, 62, 108],
    [87, 92, 109],
    [124, 123, 120],
    [166, 157, 117],
    [212, 194, 98],
    [253, 234, 69],
  ],
}

const lutCache = new Map<Colormap, Uint8ClampedArray>()

export function colormapLut(name: Colormap): Uint8ClampedArray {
  const cached = lutCache.get(name)
  if (cached) return cached
  const stops = COLORMAP_STOPS[name]
  const lut = new Uint8ClampedArray(256 * 3)
  for (let i = 0; i < 256; i++) {
    const pos = (i / 255) * (stops.length - 1)
    const k = Math.min(stops.length - 2, Math.floor(pos))
    const f = pos - k
    for (let c = 0; c < 3; c++) lut[i * 3 + c] = stops[k][c] + (stops[k + 1][c] - stops[k][c]) * f
  }
  lutCache.set(name, lut)
  return lut
}

export function colormapGradient(name: Colormap) {
  const stops = COLORMAP_STOPS[name]
  return `linear-gradient(90deg, ${stops.map((s, i) => `rgb(${s.join(',')}) ${(i / (stops.length - 1)) * 100}%`).join(', ')})`
}

export const isDefaultSettings = (s: ImageSettings) =>
  s.stretch === 'linear' && s.colormap === 'gray' && s.brightness === 0 && s.contrast === 1 && !s.invert

/** Filtro CSS equivalente para imágenes que no deben recolorearse (diferencias). */
export function cssFilterFor(s: ImageSettings) {
  const parts = [`brightness(${1 + s.brightness * 1.5})`, `contrast(${s.contrast})`]
  if (s.invert) parts.push('invert(1)')
  return parts.join(' ')
}

function stretchValue(v: number, stretch: Stretch) {
  switch (stretch) {
    case 'sqrt':
      return Math.sqrt(v)
    case 'log':
      return Math.log10(1 + 99 * v) / 2
    case 'asinh':
      return Math.asinh(10 * v) / Math.asinh(10)
    default:
      return v
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    if (!url.startsWith('data:') && !url.startsWith('blob:')) img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`No se pudo cargar ${url}`))
    img.src = url
  })
}

export async function imageToCanvas(url: string): Promise<HTMLCanvasElement> {
  const img = await loadImage(url)
  const canvas = document.createElement('canvas')
  canvas.width = img.naturalWidth
  canvas.height = img.naturalHeight
  canvas.getContext('2d')!.drawImage(img, 0, 0)
  return canvas
}

const processedCache = new Map<string, Promise<string>>()
const resolvedCache = new Map<string, string>()
const MAX_CACHE = 300

const cacheKey = (url: string, settings: ImageSettings) => `${url}|${JSON.stringify(settings)}`

/** Resultado ya calculado, sin esperar; evita parpadeos al hacer blink. */
export function getProcessedSync(url: string, settings: ImageSettings): string | undefined {
  if (isDefaultSettings(settings)) return url
  return resolvedCache.get(cacheKey(url, settings))
}

export function processImage(url: string, settings: ImageSettings): Promise<string> {
  if (isDefaultSettings(settings)) return Promise.resolve(url)
  const key = cacheKey(url, settings)
  const hit = processedCache.get(key)
  if (hit) return hit

  const job = imageToCanvas(url).then((canvas) => {
    const ctx = canvas.getContext('2d')!
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const px = data.data
    const lut = colormapLut(settings.colormap)
    const table = new Uint8ClampedArray(256)
    for (let i = 0; i < 256; i++) {
      let v = (i / 255 - 0.5) * settings.contrast + 0.5 + settings.brightness
      v = stretchValue(Math.min(1, Math.max(0, v)), settings.stretch)
      if (settings.invert) v = 1 - v
      table[i] = Math.round(v * 255)
    }
    for (let k = 0; k < px.length; k += 4) {
      const lum = Math.round(0.299 * px[k] + 0.587 * px[k + 1] + 0.114 * px[k + 2])
      const idx = table[lum] * 3
      px[k] = lut[idx]
      px[k + 1] = lut[idx + 1]
      px[k + 2] = lut[idx + 2]
    }
    ctx.putImageData(data, 0, 0)
    const out = canvas.toDataURL('image/png')
    resolvedCache.set(key, out)
    return out
  })

  processedCache.set(key, job)
  job.catch(() => processedCache.delete(key))
  if (processedCache.size > MAX_CACHE) {
    const oldest = processedCache.keys().next().value!
    processedCache.delete(oldest)
    resolvedCache.delete(oldest)
  }
  return job
}
