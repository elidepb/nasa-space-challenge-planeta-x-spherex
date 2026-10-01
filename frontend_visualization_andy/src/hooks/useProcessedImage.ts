import { useEffect, useState } from 'react'
import { getProcessedSync, processImage, type ImageSettings } from '../lib/imageProcessing'

/** Devuelve la URL procesada; mientras se calcula por primera vez, devuelve la original. */
export function useProcessedImage(url: string | null, settings: ImageSettings, enabled: boolean): string | null {
  const [, forceRender] = useState(0)
  const key = JSON.stringify(settings)

  useEffect(() => {
    if (!url || !enabled || getProcessedSync(url, settings)) return
    let cancelled = false
    processImage(url, settings)
      .then(() => !cancelled && forceRender((n) => n + 1))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [url, key, enabled])

  if (!url) return null
  if (!enabled) return url
  return getProcessedSync(url, settings) ?? url
}
