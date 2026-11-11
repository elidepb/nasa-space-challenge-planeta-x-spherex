import type { RegionQuery } from '../types/contracts'
import {
  DEFAULT_BANDPASS,
  DEFAULT_SPECTRAL_GROUP,
  normalizeBands,
  normalizeBandpass,
  primaryFromBands,
} from './spectral'

export type ViewMode = 'original' | 'swipe'
export const VIEW_MODES: ViewMode[] = ['original', 'swipe']

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
