import { useI18n } from '../i18n/I18nProvider'
import { sbdbUrl, simbadUrl } from '../lib/hunter'
import { formatDecDms, formatRaHms, formatTimestamp } from '../lib/sky'
import type { Candidate, KnownObject, ObservationSummary } from '../types/contracts'

interface ListProps {
  candidates: Candidate[]
  selectedId: string | null
  onSelect: (id: string) => void
  knownMatches: Map<string, KnownObject>
}

export function CandidateList({ candidates, selectedId, onSelect, knownMatches }: ListProps) {
  const { t } = useI18n()
  return (
    <section className="panel">
      <h2 className="panel-title">
        {t('candidates.title')} <span className="muted">({candidates.length})</span>
      </h2>
      {candidates.length === 0 ? (
        <p className="muted small">{t('candidates.empty')}</p>
      ) : (
        <ul className="cand-list">
          {candidates.map((c) => (
            <li key={c.id}>
              <button className={`cand-item ${c.id === selectedId ? 'active' : ''}`} onClick={() => onSelect(c.id)}>
                <span className={`status-dot status-${c.status}`} />
                <span className="cand-id">{c.id}</span>
                <span className="muted small">{t('candidates.perYear', { v: c.motionArcsecPerYear.toFixed(1) })}</span>
                {c.status !== 'artifact' && c.status !== 'rejected' && (
                  <span className={`tag ${knownMatches.has(c.id) ? 'tag-known' : 'tag-new'}`}>
                    {knownMatches.has(c.id) ? t('candidates.known') : t('candidates.new')}
                  </span>
                )}
                <span className="snr">
                  {t('candidates.snr')} {c.snr.toFixed(1)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

interface DetailsProps {
  candidate: Candidate | null
  observations: ObservationSummary[]
  activeObservationId: string | null
  onSelectObservation: (index: number) => void
  knownMatch: KnownObject | null
}

export function CandidateDetails({ candidate, observations, activeObservationId, onSelectObservation, knownMatch }: DetailsProps) {
  const { t } = useI18n()

  if (!candidate) {
    return (
      <section className="panel grow">
        <h2 className="panel-title">{t('candidates.detailsTitle')}</h2>
        <p className="muted small">{t('candidates.selectHint')}</p>
      </section>
    )
  }

  const indexOf = (id: string) => observations.findIndex((o) => o.id === id)

  return (
    <section className="panel grow">
      <h2 className="panel-title">
        {candidate.id}
        <span className={`tag status-${candidate.status}`}>{t(`candidateStatus.${candidate.status}`)}</span>
      </h2>
      <dl className="details">
        <dt>{t('candidates.ra')}</dt>
        <dd>
          {formatRaHms(candidate.ra)} <span className="muted">({candidate.ra.toFixed(5)}°)</span>
        </dd>
        <dt>{t('candidates.dec')}</dt>
        <dd>
          {formatDecDms(candidate.dec)} <span className="muted">({candidate.dec.toFixed(5)}°)</span>
        </dd>
        <dt>{t('candidates.displacement')}</dt>
        <dd>{candidate.displacementArcsec.toFixed(2)}″</dd>
        <dt>{t('candidates.motion')}</dt>
        <dd>{t('candidates.perYear', { v: candidate.motionArcsecPerYear.toFixed(2) })}</dd>
        <dt>{t('candidates.snr')}</dt>
        <dd>{candidate.snr.toFixed(1)}</dd>
      </dl>

      {candidate.status !== 'artifact' &&
        (knownMatch ? (
          <div className="verdict known small">
            <strong>✓ {t('candidates.knownAs', { name: knownMatch.name })}</strong>
            <a href={sbdbUrl(knownMatch.name)} target="_blank" rel="noreferrer">
              {t('hunter.openSbdb')} ↗
            </a>
          </div>
        ) : (
          <div className="verdict new small">
            <strong>🚀 {t('candidates.notInCatalogs')}</strong>
          </div>
        ))}
      <div className="row gap wrap">
        <a className="chip" href={simbadUrl(candidate.ra, candidate.dec)} target="_blank" rel="noreferrer">
          SIMBAD ↗
        </a>
      </div>

      <h3 className="subtitle">{t('candidates.detections', { n: candidate.detections.length })}</h3>
      <table className="det-table">
        <thead>
          <tr>
            <th>{t('candidates.table.index')}</th>
            <th>{t('candidates.table.date')}</th>
            <th>{t('candidates.table.position')}</th>
            <th>{t('candidates.table.snr')}</th>
          </tr>
        </thead>
        <tbody>
          {candidate.detections.map((d) => {
            const idx = indexOf(d.observationId)
            return (
              <tr
                key={d.observationId}
                className={d.observationId === activeObservationId ? 'active' : ''}
                onClick={() => idx >= 0 && onSelectObservation(idx)}
              >
                <td>{idx + 1}</td>
                <td>{formatTimestamp(d.timestamp).slice(0, 10)}</td>
                <td>
                  {d.x.toFixed(1)}, {d.y.toFixed(1)}
                </td>
                <td>{d.snr?.toFixed(1) ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
