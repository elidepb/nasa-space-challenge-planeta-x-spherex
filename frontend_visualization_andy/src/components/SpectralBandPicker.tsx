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
  /** Índices globales 1–102 (solo 1 banda; el API no multiplica). */
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
  const [hover, setHover] = useState<{ index: number; lambda: number } | null>(null)
  const dragging = useRef(false)

  function selectBand(bandIndex: number) {
    if (disabled) return
    onChange([bandIndex])
  }

  function onSegmentPointerDown(bandIndex: number, e: ReactPointerEvent<HTMLButtonElement>) {
    if (disabled) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    dragging.current = true
    selectBand(bandIndex)
  }

  function onSegmentPointerEnter(bandIndex: number) {
    const band = partsFromBandIndex(bandIndex)
    setHover({ index: bandIndex, lambda: band.wlCenter })
    if (!dragging.current) return
    selectBand(bandIndex)
  }

  function endDrag() {
    dragging.current = false
  }

  const badgeReadout = hover
    ? `#${hover.index} · ${hover.lambda.toFixed(3)} μm`
    : `#${primary.bandIndex} · ${primary.wlCenter.toFixed(3)} μm★`

  return (
    <div className={`spectral-picker ${disabled ? 'disabled' : ''}`}>
      <div className="spectral-picker-head">
        <div className="spectral-picker-head-left">
          <span className="spectral-ruler-title">SPHEREX BANDS · 102</span>
          <span className="spectral-ruler-readout">
            {t('search.bandsSelected', { n: sorted.length, max: MAX_SELECTED_BANDS, total: TOTAL_BANDS })}
          </span>
        </div>
        <div className="spectral-picker-head-right">
          <span className="chip spectral-selected-chip active">
            {badgeReadout}
          </span>
        </div>
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
            return (
              <button
                key={b.bandIndex}
                type="button"
                className={`spectral-rail-seg ${on ? 'active primary' : ''}`}
                disabled={disabled}
                aria-pressed={on}
                aria-label={`#${b.bandIndex} ${b.wlCenter.toFixed(3)} μm`}
                title={`#${b.bandIndex} · ${b.wlCenter.toFixed(3)} μm`}
                onPointerDown={(e) => onSegmentPointerDown(b.bandIndex, e)}
                onPointerEnter={() => onSegmentPointerEnter(b.bandIndex)}
              />
            )
          })}
        </div>
        <div className="spectral-spectrum-labels">
          <span>#1 · 0.75 μm</span>
          <span className="spectral-hint-text">{t('search.bandsHint', { max: MAX_SELECTED_BANDS })}</span>
          <span>#102 · 5.0 μm</span>
        </div>
      </div>
    </div>
  )
}
