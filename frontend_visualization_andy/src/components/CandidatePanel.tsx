import { useI18n } from '../i18n/I18nProvider'
import { sbdbUrl, simbadUrl } from '../lib/hunter'
import { formatDecDms, formatRaHms } from '../lib/sky'
import type { Candidate, KnownObject } from '../types/contracts'

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
                <span className="muted small">
                  {t('candidates.perYear', {
                    v: Number.isFinite(c.motionArcsecPerYear) ? c.motionArcsecPerYear.toFixed(1) : '—',
                  })}
                </span>
                {c.status !== 'artifact' && c.status !== 'rejected' && (
                  <span className={`tag ${knownMatches.has(c.id) ? 'tag-known' : 'tag-new'}`}>
                    {knownMatches.has(c.id) ? t('candidates.known') : t('candidates.new')}
                  </span>
                )}
                <span className="snr">
                  {t('candidates.snr')} {Number.isFinite(c.snr) ? c.snr.toFixed(1) : '—'}
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
  knownMatch: KnownObject | null
}

export function CandidateDetails({ candidate, knownMatch }: DetailsProps) {
  const { t } = useI18n()

  if (!candidate) {
    return (
      <section className="panel grow">
        <h2 className="panel-title">{t('candidates.detailsTitle')}</h2>
        <p className="muted small">{t('candidates.selectHint')}</p>
      </section>
    )
  }

  return (
    <section className="panel grow">
      <h2 className="panel-title">
        {candidate.id}
        <span className={`tag status-${candidate.status}`}>{t(`candidateStatus.${candidate.status}`)}</span>
      </h2>
      <dl className="details">
        <dt>{t('candidates.ra')}</dt>
        <dd>
          {Number.isFinite(candidate.ra) ? (
            <>
              {formatRaHms(candidate.ra)} <span className="muted">({candidate.ra.toFixed(5)}°)</span>
            </>
          ) : (
            <span className="muted">—</span>
          )}
        </dd>
        <dt>{t('candidates.dec')}</dt>
        <dd>
          {Number.isFinite(candidate.dec) ? (
            <>
              {formatDecDms(candidate.dec)} <span className="muted">({candidate.dec.toFixed(5)}°)</span>
            </>
          ) : (
            <span className="muted">—</span>
          )}
        </dd>
        <dt>{t('candidates.displacement')}</dt>
        <dd>
          {Number.isFinite(candidate.displacementArcsec) ? `${candidate.displacementArcsec.toFixed(2)}″` : '—'}
        </dd>
        <dt>{t('candidates.motion')}</dt>
        <dd>
          {t('candidates.perYear', {
            v: Number.isFinite(candidate.motionArcsecPerYear) ? candidate.motionArcsecPerYear.toFixed(2) : '—',
          })}
        </dd>
        <dt>{t('candidates.snr')}</dt>
        <dd>{Number.isFinite(candidate.snr) ? candidate.snr.toFixed(1) : '—'}</dd>
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
      {Number.isFinite(candidate.ra) && Number.isFinite(candidate.dec) && (
        <div className="row gap wrap">
          <a className="chip" href={simbadUrl(candidate.ra, candidate.dec)} target="_blank" rel="noreferrer">
            SIMBAD ↗
          </a>
        </div>
      )}
    </section>
  )
}
