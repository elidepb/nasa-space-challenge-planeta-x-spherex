import { useMemo } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { getAllBands, normalizeBands, partsFromBandIndex, TOTAL_BANDS } from '../lib/spectral'

interface Props {
  /** Índices globales 1–102 seleccionados (multi). */
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

  function toggle(bandIndex: number) {
    if (disabled) return
    const next = new Set(selectedSet)
    if (next.has(bandIndex)) {
      if (next.size <= 1) return
      next.delete(bandIndex)
    } else {
      next.add(bandIndex)
    }
    onChange([...next].sort((a, b) => a - b))
  }

  function selectAll() {
    if (disabled) return
    onChange(all.map((b) => b.bandIndex))
  }

  function clearToPrimary() {
    if (disabled) return
    onChange([primary.bandIndex])
  }

  return (
    <div className={`spectral-picker ${disabled ? 'disabled' : ''}`}>
      <div className="spectral-picker-head">
        <span className="spectral-ruler-title">{t('search.bandsTitle')}</span>
        <span className="spectral-ruler-readout">
          {t('search.bandsSelected', { n: sorted.length, total: TOTAL_BANDS })}
        </span>
      </div>
      <p className="muted small spectral-picker-hint">{t('search.bandsHint')}</p>

      <div className="spectral-picker-actions">
        <button type="button" className="chip" disabled={disabled} onClick={selectAll}>
          {t('search.bandsSelectAll')}
        </button>
        <button type="button" className="chip" disabled={disabled || sorted.length <= 1} onClick={clearToPrimary}>
          {t('search.bandsClear')}
        </button>
      </div>

      <div className="spectral-spectrum" aria-hidden>
        <div className="spectral-spectrum-bar" />
        <div className="spectral-spectrum-labels">
          <span>0.75 μm</span>
          <span>5.0 μm</span>
        </div>
      </div>

      <div className="spectral-band-strip" role="group" aria-label={t('search.bandsTitle')}>
        {all.map((b) => {
          const on = selectedSet.has(b.bandIndex)
          const isPrimary = b.bandIndex === primary.bandIndex
          return (
            <button
              key={b.bandIndex}
              type="button"
              className={`spectral-band-pill ${on ? 'active' : ''} ${isPrimary ? 'primary' : ''}`}
              disabled={disabled}
              aria-pressed={on}
              title={`#${b.bandIndex} · ${b.wlCenter.toFixed(3)} μm`}
              onClick={() => toggle(b.bandIndex)}
            >
              {b.bandIndex}
            </button>
          )
        })}
      </div>

      {sorted.length > 1 && (
        <div className="spectral-selected-chips">
          <span className="muted small">{t('search.bandsChosen')}</span>
          <div className="spectral-selected-list">
            {sorted.map((i) => (
              <button
                key={i}
                type="button"
                className={`chip spectral-selected-chip ${i === primary.bandIndex ? 'active' : ''}`}
                disabled={disabled}
                title={t('search.bandsRemove', { n: i })}
                onClick={() => toggle(i)}
              >
                #{i}
                {i === primary.bandIndex ? ' ★' : ' ×'}
              </button>
            ))}
          </div>
        </div>
      )}

      <p className="spectral-hint muted small">
        {t('search.bandsPrimary', {
          band: `#${primary.bandIndex}`,
          index: primary.bandIndex,
          lambda: primary.wlCenter.toFixed(3),
        })}
      </p>
    </div>
  )
}
