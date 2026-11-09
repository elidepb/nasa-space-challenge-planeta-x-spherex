import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { AnalysisInfo, AnalysisResult, RegionQuery } from '../types/contracts'

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
      const [observations, candidates, images, knownObjects] = await Promise.all([
        api.getObservations(info.id),
        api.getCandidates(info.id),
        api.getImages(info.id),
        api.getKnownObjects(info.id),
      ])
      if (!alive()) return
      setState({
        phase: 'completed',
        info,
        result: { analysis: info, observations, candidates, images, knownObjects },
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
