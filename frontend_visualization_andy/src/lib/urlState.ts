import { useCallback, useEffect, useState } from 'react'
import type { RegionQuery } from '../types/contracts'
import {
  DEFAULT_BANDPASS,
  DEFAULT_SPECTRAL_GROUP,
  normalizeBands,
  normalizeBandpass,
  primaryFromBands,
} from './spectral'

export type ViewMode = 'original' | 'swipe' | 'blink'
export const VIEW_MODES: ViewMode[] = ['original', 'swipe', 'blink']

export interface UrlState {
  query: RegionQuery | null
  mode?: ViewMode
  /** Índice de época (0-based). En la URL se guarda 1-based. */
  epoch?: number
  candidate?: string
}

function parseBandsParam(raw: string | null): number[] | undefined {
  if (!raw?.trim()) return undefined
  const out: number[] = []
  for (const part of raw.split(',')) {
    const n = Number(part.trim())
    if (Number.isFinite(n)) out.push(n)
  }
  return out.length ? out : undefined
}

export function readUrlState(): UrlState {
  const p = new URLSearchParams(window.location.search)
  const num = (k: string) => {
    const v = p.get(k)
    return v === null || v.trim() === '' ? NaN : Number(v)
  }
  const ra = num('ra')
  const dec = num('dec')
  const size = num('size')
  const bandpass = normalizeBandpass(p.get('band') ?? DEFAULT_BANDPASS)
  const groupRaw = num('group')
  const group = Number.isFinite(groupRaw) ? groupRaw : DEFAULT_SPECTRAL_GROUP
  const bands = normalizeBands(parseBandsParam(p.get('bands')), bandpass, group)
  const primary = primaryFromBands(bands)
  const query =
    Number.isFinite(ra) && Number.isFinite(dec)
      ? {
          ra,
          dec,
          size: Number.isFinite(size) ? size : 0.85,
          qr: p.get('qr') ?? 'qr2',
          bandpass: primary.bandpass,
          group: primary.group,
          bands,
        }
      : null
  const mode = p.get('mode') as ViewMode | null
  const epoch = num('epoch')
  return {
    query,
    mode: mode && VIEW_MODES.includes(mode) ? mode : undefined,
    epoch: Number.isInteger(epoch) && epoch >= 1 ? epoch - 1 : undefined,
    candidate: p.get('cand') ?? undefined,
  }
}

export function writeUrlState(state: UrlState) {
  const p = new URLSearchParams()
  if (state.query) {
    p.set('ra', String(state.query.ra))
    p.set('dec', String(state.query.dec))
    p.set('size', String(state.query.size))
    if (state.query.qr) p.set('qr', state.query.qr)
    const bands = normalizeBands(state.query.bands, state.query.bandpass, state.query.group)
    const primary = primaryFromBands(bands)
    p.set('band', primary.bandpass)
    p.set('group', String(primary.group))
  }
  if (state.mode && state.mode !== 'original') p.set('mode', state.mode)
  if (state.epoch !== undefined) p.set('epoch', String(state.epoch + 1))
  if (state.candidate) p.set('cand', state.candidate)
  const search = p.toString()
  const url = `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`
  if (url !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.replaceState(null, '', url)
  }
}

// ============================================================================
// WiseView-Style Hash State Synchronizer (#ra=...&dec=...&diff=1&pmra=...)
// ============================================================================

export interface ViewerUrlState {
  ra: number
  dec: number
  band: string
  mode: 'original' | 'swipe' | 'blink'
  diff: boolean // Activa la imagen residual (sin estrellas fijas)
  gaia: boolean // Muestra overlay de Gaia DR3
  pmra: number // Desplazamiento Track & Stack en RA (mas/yr)
  pmdec: number // Desplazamiento Track & Stack en Dec (mas/yr)
  speed: number // Velocidad del blink en ms
}

const DEFAULT_WISE_STATE: ViewerUrlState = {
  ra: 133.7862,
  dec: -7.2443,
  band: 'D1',
  mode: 'blink',
  diff: false,
  gaia: true,
  pmra: 0,
  pmdec: 0,
  speed: 500,
}

export function useWiseViewUrlState(): [ViewerUrlState, (patch: Partial<ViewerUrlState>) => void] {
  const parseHash = (): ViewerUrlState => {
    const raw = typeof window !== 'undefined' ? window.location.hash.replace(/^#/, '') : ''
    const params = new URLSearchParams(raw)
    return {
      ra: parseFloat(params.get('ra') || '') || DEFAULT_WISE_STATE.ra,
      dec: parseFloat(params.get('dec') || '') || DEFAULT_WISE_STATE.dec,
      band: params.get('band') || DEFAULT_WISE_STATE.band,
      mode: (params.get('mode') as ViewerUrlState['mode']) || DEFAULT_WISE_STATE.mode,
      diff: params.get('diff') === '1',
      gaia: params.get('gaia') !== '0',
      pmra: parseFloat(params.get('pmra') || '0'),
      pmdec: parseFloat(params.get('pmdec') || '0'),
      speed: parseInt(params.get('speed') || '500', 10),
    }
  }

  const [state, setState] = useState<ViewerUrlState>(parseHash)

  const updateState = useCallback((patch: Partial<ViewerUrlState>) => {
    setState((prev) => {
      const next = { ...prev, ...patch }
      const params = new URLSearchParams()
      params.set('ra', next.ra.toFixed(6))
      params.set('dec', next.dec.toFixed(6))
      params.set('band', next.band)
      params.set('mode', next.mode)
      params.set('diff', next.diff ? '1' : '0')
      params.set('gaia', next.gaia ? '1' : '0')
      if (next.pmra !== 0) params.set('pmra', String(next.pmra))
      if (next.pmdec !== 0) params.set('pmdec', String(next.pmdec))
      params.set('speed', String(next.speed))

      if (typeof window !== 'undefined') {
        window.history.replaceState(null, '', `#${params.toString()}`)
      }
      return next
    })
  }, [])

  useEffect(() => {
    const onHashChange = () => setState(parseHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return [state, updateState]
}
