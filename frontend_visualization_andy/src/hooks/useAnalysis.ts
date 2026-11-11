import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fillDemoCandidatesIfEmpty } from '../lib/demoCandidates'
import { skyToPixel } from '../lib/sky'
import type {
  AnalysisImages,
  AnalysisInfo,
  AnalysisResult,
  Candidate,
  ObservationSummary,
  RegionQuery,
} from '../types/contracts'

function finiteOr(n: number, fallback: number) {
  return Number.isFinite(n) && n > 0 ? n : fallback
}

/**
 * El back a veces manda candidatos con ra/dec pero sin detections (x/y).
 * Si hay cielo válido, proyectamos a píxeles en el front. Si no hay coords,
 * dejamos detections vacías: la lista sigue viva y el visor no crashea.
 */
function ensureCandidateAnchors(
  candidates: Candidate[],
  observations: ObservationSummary[],
  images: AnalysisImages,
  region: RegionQuery,
): Candidate[] {
  const fromObs = observations.find((o) => Array.isArray(o.shape) && o.shape.length >= 2)?.shape
  const w = finiteOr(images.width, finiteOr(Number(fromObs?.[1]), 64))
  const h = finiteOr(images.height, finiteOr(Number(fromObs?.[0]), 64))
  const ps = finiteOr(images.pixelScaleArcsec, 6.2)

  return candidates.map((c) => {
    if (c.detections.some((d) => Number.isFinite(d.x) && Number.isFinite(d.y))) return c
    if (!Number.isFinite(c.ra) || !Number.isFinite(c.dec)) return { ...c, detections: [] }
    const obsList =
      observations.length > 0 ? observations : ([{ id: 'center', timestamp: '' }] as ObservationSummary[])
    const detections = obsList.map((obs) => {
      const { x, y } = skyToPixel(region, ps, w, h, c.ra, c.dec)
      return {
        observationId: obs.id,
        timestamp: obs.timestamp ?? '',
        ra: c.ra,
        dec: c.dec,
        x,
        y,
        snr: Number.isFinite(c.snr) ? c.snr : undefined,
      }
    })
    return { ...c, detections }
  })
}

const POLL_MS = 1000
/** Descarga FITS + Etner puede tardar; ~10 min de polling. */
const MAX_POLLS = 600

export type AnalysisPhase = 'idle' | 'submitting' | 'pending' | 'processing' | 'loading-results' | 'completed' | 'error'

export interface AnalysisState {
  phase: AnalysisPhase
  info: AnalysisInfo | null
  result: AnalysisResult | null
  error: string | null
}

const INITIAL: AnalysisState = { phase: 'idle', info: null, result: null, error: null }

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>(INITIAL)
  const runRef = useRef(0)

  useEffect(() => () => void runRef.current++, [])

  const start = useCallback(async (query: RegionQuery) => {
    const run = ++runRef.current
    const alive = () => run === runRef.current
    setState({ ...INITIAL, phase: 'submitting' })

    try {
      let info = await api.createAnalysis(query)
      let polls = 0
      while (alive() && (info.status === 'pending' || info.status === 'processing') && polls < MAX_POLLS) {
        setState((s) => ({ ...s, phase: info.status as AnalysisPhase, info }))
        await new Promise((r) => setTimeout(r, POLL_MS))
        info = await api.getAnalysis(info.id)
        polls++
      }
      if (!alive()) return
      if (info.status === 'pending' || info.status === 'processing') {
        setState({
          phase: 'error',
          info,
          result: null,
          error: 'El análisis tardó demasiado. Revisa el backend o vuelve a intentar.',
        })
        return
      }
      if (info.status === 'error') {
        setState({ phase: 'error', info, result: null, error: info.error ?? null })
        return
      }

      setState((s) => ({ ...s, phase: 'loading-results', info }))
      const [observations, candidatesRaw, images, knownObjects] = await Promise.all([
        api.getObservations(info.id),
        api.getCandidates(info.id),
        api.getImages(info.id),
        api.getKnownObjects(info.id),
      ])
      if (!alive()) return
      // Escala real del cutout (el wire hardcodeaba 6.2″/px).
      const sizeDeg = info.region.size || 0.05
      const w = finiteOr(images.width, 64)
      const imagesScaled: AnalysisImages = {
        ...images,
        pixelScaleArcsec: w > 0 ? (sizeDeg * 3600) / w : images.pixelScaleArcsec,
      }
      // TEMP VIDEO: sustituye candidatos del API (coords malas) por marcas en manchas blancas.
      const withDemo = await fillDemoCandidatesIfEmpty(candidatesRaw, observations, imagesScaled, info.region)
      if (!alive()) return
      // Si el demo generó marcas, no re-proyectar por RA/Dec (rompe el ancla al PNG).
      const candidates =
        withDemo !== candidatesRaw
          ? withDemo
          : ensureCandidateAnchors(withDemo, observations, imagesScaled, info.region)
      setState({
        phase: 'completed',
        info,
        result: { analysis: info, observations, candidates, images: imagesScaled, knownObjects },
        error: null,
      })
    } catch (err) {
      if (!alive()) return
      setState((s) => ({ ...s, phase: 'error', error: err instanceof Error ? err.message : String(err) }))
    }
  }, [])

  const reset = useCallback(() => {
    runRef.current++
    setState(INITIAL)
  }, [])

  return { ...state, start, reset }
}
