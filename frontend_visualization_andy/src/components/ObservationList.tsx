import { useI18n } from '../i18n/I18nProvider'
import { formatTimestamp } from '../lib/sky'
import type { ObservationSummary } from '../types/contracts'

interface Props {
  observations: ObservationSummary[]
  activeIndex: number
  referenceId: string | null
  onSelect: (index: number) => void
}

export function ObservationList({ observations, activeIndex, referenceId, onSelect }: Props) {
  const { t } = useI18n()
  return (
    <section className="panel grow">
      <h2 className="panel-title">
        {t('observations.title')} <span className="muted">({observations.length})</span>
      </h2>
      {observations.length === 0 ? (
        <p className="muted small">{t('observations.empty')}</p>
      ) : (
        <ol className="obs-list">
          {observations.map((o, i) => (
            <li key={o.id}>
              <button className={`obs-item ${i === activeIndex ? 'active' : ''}`} onClick={() => onSelect(i)}>
                <span className="obs-index">{i + 1}</span>
                <span className="obs-main">
                  <span className="obs-date">
                    {o.timestamp ? formatTimestamp(o.timestamp) : o.id}
                  </span>
                  <span className="muted small">
                    {t('observations.detector', { d: o.detector })} · {o.wavelength?.toFixed(3) ?? '—'} {o.spectral_unit}
                    {typeof o.metadata?.survey_index === 'number' ? ` · survey ${o.metadata.survey_index}` : ''}
                  </span>
                </span>
                {o.id === referenceId && <span className="tag">{t('observations.reference')}</span>}
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
