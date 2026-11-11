import { useI18n } from '../i18n/I18nProvider'
import { timestampMs } from '../lib/sky'
import type { ObservationSummary } from '../types/contracts'

interface Props {
  observations: ObservationSummary[]
  activeIndex: number
  referenceIndex: number
  onSelect: (index: number) => void
}

/** Línea de tiempo con las épocas espaciadas según su fecha real. */
export function Timeline({ observations, activeIndex, referenceIndex, onSelect }: Props) {
  const { t } = useI18n()
  if (observations.length === 0) return null
  const times = observations.map((o) => timestampMs(o.timestamp))
  const valid = times.map((ms, i) => ({ ms, i })).filter((t) => Number.isFinite(t.ms))
  // Si las fechas vienen mal del backend, no tumbar toda la UI con toISOString(NaN).
  const t0 = valid[0]?.ms ?? 0
  const t1 = valid[valid.length - 1]?.ms ?? t0
  const span = Math.max(1, t1 - t0)
  const pos = (i: number) => {
    if (observations.length === 1) return 50
    const ms = times[i]
    if (!Number.isFinite(ms)) return (i / Math.max(1, observations.length - 1)) * 100
    return ((ms - t0) / span) * 100
  }
  const fmt = (ms: number) => {
    if (!Number.isFinite(ms)) return '—'
    try {
      return new Date(ms).toISOString().slice(0, 10)
    } catch {
      return '—'
    }
  }

  return (
    <div className="timeline">
      <div className="timeline-track">
        <div className="timeline-progress" style={{ width: `${pos(activeIndex)}%` }} />
        {observations.map((o, i) => (
          <button
            key={o.id}
            className={`timeline-dot ${i === activeIndex ? 'active' : ''} ${i === referenceIndex ? 'ref' : ''}`}
            style={{ left: `${pos(i)}%` }}
            title={t('timeline.epochTitle', { n: i + 1, date: o.timestamp })}
            onClick={() => onSelect(i)}
          />
        ))}
      </div>
      <div className="timeline-labels muted small">
        <span>{fmt(t0)}</span>
        <span>{t('timeline.epochOf', { n: activeIndex + 1, total: observations.length })}</span>
        <span>{fmt(times[times.length - 1])}</span>
      </div>
    </div>
  )
}
