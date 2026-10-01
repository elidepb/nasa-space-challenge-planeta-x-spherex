import { applyPalette, GIFEncoder, quantize } from 'gifenc'
import { imageToCanvas } from './imageProcessing'

export interface GifFrame {
  url: string
  label: string
}

const OUTPUT_SIZE = 480

/** Genera un GIF animado (frames ampliados sin suavizado + etiqueta) y lo descarga. */
export async function exportGif(frames: GifFrame[], delayMs: number, filename: string, title: string) {
  if (frames.length === 0) return
  const canvas = document.createElement('canvas')
  canvas.width = OUTPUT_SIZE
  canvas.height = OUTPUT_SIZE
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  const gif = GIFEncoder()

  for (const frame of frames) {
    const source = await imageToCanvas(frame.url)
    ctx.imageSmoothingEnabled = false
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, OUTPUT_SIZE, OUTPUT_SIZE)
    ctx.drawImage(source, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE)

    ctx.fillStyle = 'rgba(7, 10, 18, 0.75)'
    ctx.fillRect(0, OUTPUT_SIZE - 30, OUTPUT_SIZE, 30)
    ctx.fillStyle = '#e3e9f6'
    ctx.font = '600 14px Segoe UI, system-ui, sans-serif'
    ctx.textBaseline = 'middle'
    ctx.fillText(frame.label, 10, OUTPUT_SIZE - 15)
    ctx.textAlign = 'right'
    ctx.fillStyle = '#8592ad'
    ctx.fillText(title, OUTPUT_SIZE - 10, OUTPUT_SIZE - 15)
    ctx.textAlign = 'left'

    const { data } = ctx.getImageData(0, 0, OUTPUT_SIZE, OUTPUT_SIZE)
    const palette = quantize(data, 256)
    gif.writeFrame(applyPalette(data, palette), OUTPUT_SIZE, OUTPUT_SIZE, { palette, delay: delayMs })
  }

  gif.finish()
  const blob = new Blob([gif.bytes() as BlobPart], { type: 'image/gif' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 5000)
}
