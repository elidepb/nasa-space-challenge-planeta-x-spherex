import type { RegionQuery } from '../types/contracts'
import {
  clampSpectralGroup,
  DEFAULT_BANDPASS,
  DEFAULT_SPECTRAL_GROUP,
  normalizeBandpass,
} from './spectral'

export type ViewMode = 'original' | 'blink' | 'difference' | 'swipe'
export const VIEW_MODES: ViewMode[] = ['original', 'blink', 'difference', 'swipe']

export interface UrlState {
  query: RegionQuery | null
  mode?: ViewMode
  /** Índice de época (0-based). En la URL se guarda 1-based. */
  epoch?: number
  candidate?: string
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
  const groupRaw = num('group')
  const query =
    Number.isFinite(ra) && Number.isFinite(dec)
      ? {
          ra,
          dec,
          size: Number.isFinite(size) ? size : 0.05,
          qr: p.get('qr') ?? 'qr2',
          bandpass: normalizeBandpass(p.get('band') ?? DEFAULT_BANDPASS),
          group: Number.isFinite(groupRaw) ? clampSpectralGroup(groupRaw) : DEFAULT_SPECTRAL_GROUP,
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
    if (state.query.bandpass) p.set('band', state.query.bandpass)
    if (state.query.group != null) p.set('group', String(clampSpectralGroup(state.query.group)))
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
