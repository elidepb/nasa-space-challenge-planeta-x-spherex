import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import {
  getAllBands,
  MAX_SELECTED_BANDS,
  normalizeBands,
  partsFromBandIndex,
  TOTAL_BANDS,
} from '../lib/spectral'

interface Props {
  /** Índices globales 1–102 seleccionados (máx. MAX_SELECTED_BANDS). */
  selected: number[]
  disabled?: boolean
  onChange: (bands: number[]) => void
}

export function SpectralBandPicker({ selected, disabled, onChange }: Props) {
  const { t } = useI18n()
  const all = useMemo(() => getAllBands(), [])
  const selectedSet = useMemo(() => new Set(normalizeBands(selected)), [selected])
  const sorted = useMemo(() => [...selectedSet].sort((a, b) => a - b), [selectedSet])
  const primary = partsFromBandIndex(sorted[0] ?? 1)
  const atMax = selectedSet.size >= MAX_SELECTED_BANDS
  const [hover, setHover] = useState<{ index: number; lambda: number } | null>(null)
  const dragMode = useRef<'add' | 'remove' | null>(null)

  function applyToggle(bandIndex: number, mode: 'add' | 'remove' | 'flip') {
    if (disabled) return
    const next = new Set(selectedSet)
    if (mode === 'add') {
      if (next.has(bandIndex)) return
      if (next.size >= MAX_SELECTED_BANDS) return
      next.add(bandIndex)
    } else if (mode === 'remove') {
      if (next.size <= 1 && next.has(bandIndex)) return
      next.delete(bandIndex)
    } else if (next.has(bandIndex)) {
      if (next.size <= 1) return
      next.delete(bandIndex)
    } else {
      if (next.size >= MAX_SELECTED_BANDS) return
      next.add(bandIndex)
    }
    onChange([...next].sort((a, b) => a - b))
  }

  function onSegmentPointerDown(bandIndex: number, e: ReactPointerEvent<HTMLButtonElement>) {
    if (disabled) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    const mode = selectedSet.has(bandIndex) ? 'remove' : 'add'
    if (mode === 'add' && atMax) {
      dragMode.current = null
      return
    }
    dragMode.current = mode
    applyToggle(bandIndex, mode)
  }

  function onSegmentPointerEnter(bandIndex: number) {
    const band = partsFromBandIndex(bandIndex)
    setHover({ index: bandIndex, lambda: band.wlCenter })
    if (!dragMode.current) return
    applyToggle(bandIndex, dragMode.current)
  }

  function endDrag() {
    dragMode.current = null
  }

  function clearToPrimary() {
    if (disabled) return
    onChange([primary.bandIndex])
  }

  const readout = hover
    ? t('search.bandsHover', { n: hover.index, lambda: hover.lambda.toFixed(3) })
    : atMax
      ? t('search.bandsMaxHint', { max: MAX_SELECTED_BANDS })
      : t('search.bandsPrimary', {
          band: `#${primary.bandIndex}`,
          index: primary.bandIndex,
          lambda: primary.wlCenter.toFixed(3),
        })

  return (
    <div className={`spectral-picker ${disabled ? 'disabled' : ''}`}>
      <div className="spectral-picker-head">
        <span className="spectral-ruler-title">{t('search.bandsTitle')}</span>
        <span className="spectral-ruler-readout">
          {t('search.bandsSelected', { n: sorted.length, max: MAX_SELECTED_BANDS, total: TOTAL_BANDS })}
        </span>
      </div>

      <div className="spectral-picker-actions">
        <button type="button" className="chip" disabled={disabled || sorted.length <= 1} onClick={clearToPrimary}>
          {t('search.bandsClear')}
        </button>
      </div>

      <div
        className="spectral-rail"
        role="group"
        aria-label={t('search.bandsTitle')}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={() => {
          endDrag()
          setHover(null)
        }}
      >
        <div className="spectral-rail-track">
          {all.map((b) => {
            const on = selectedSet.has(b.bandIndex)
            const isPrimary = b.bandIndex === primary.bandIndex
            const blocked = !on && atMax
            return (
              <button
                key={b.bandIndex}
                type="button"
                className={`spectral-rail-seg ${on ? 'active' : ''} ${isPrimary ? 'primary' : ''} ${blocked ? 'blocked' : ''}`}
                disabled={disabled}
                aria-pressed={on}
                aria-disabled={blocked || undefined}
                aria-label={`#${b.bandIndex} ${b.wlCenter.toFixed(3)} μm`}
                title={
                  blocked
                    ? t('search.bandsMaxHint', { max: MAX_SELECTED_BANDS })
                    : `#${b.bandIndex} · ${b.wlCenter.toFixed(3)} μm`
                }
                onPointerDown={(e) => onSegmentPointerDown(b.bandIndex, e)}
                onPointerEnter={() => onSegmentPointerEnter(b.bandIndex)}
              />
            )
          })}
        </div>
        <div className="spectral-spectrum-labels">
          <span>#1 · 0.75 μm</span>
          <span>#102 · 5.0 μm</span>
        </div>
      </div>

      <p className="spectral-rail-readout muted small">{readout}</p>
      <p className="muted small">{t('search.bandsHint', { max: MAX_SELECTED_BANDS })}</p>

      {sorted.length > 0 && (
        <div className="spectral-selected-list compact">
          {sorted.map((i) => (
            <button
              key={i}
              type="button"
              className={`chip spectral-selected-chip ${i === primary.bandIndex ? 'active' : ''}`}
              disabled={disabled}
              title={t('search.bandsRemove', { n: i })}
              onClick={() => applyToggle(i, 'flip')}
            >
              #{i}
              {i === primary.bandIndex ? ' ★' : ''}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
