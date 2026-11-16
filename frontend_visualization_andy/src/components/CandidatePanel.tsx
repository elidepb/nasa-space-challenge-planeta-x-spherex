import { useEffect, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { simbadUrl, type KnownCatalogObject } from '../lib/hunter'
import { formatDecDms, formatRaHms } from '../lib/sky'
import type { Candidate, KnownObject } from '../types/contracts'

interface ListProps {
  candidates: Candidate[]
  selectedId: string | null
  onSelect: (id: string) => void
  knownMatches: Map<string, KnownObject>
  liveCatalogMatches?: Map<string, KnownCatalogObject>
}

export function CandidateList({ candidates, selectedId, onSelect, knownMatches, liveCatalogMatches }: ListProps) {
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
          {candidates.map((c) => {
            const liveMatch = liveCatalogMatches?.get(c.id)
            const isKnown = knownMatches.has(c.id) || !!liveMatch
            const isPlanetXCandidate = !isKnown && c.snr >= 4.5

            return (
              <li key={c.id}>
                <button
                  className={`cand-item ${c.id === selectedId ? 'active' : ''}`}
                  onClick={() => onSelect(c.id)}
                >
                  <span className={`status-dot status-${c.status}`} />
                  <span className="cand-id">{c.id}</span>
                  <span className="muted small">
                    {t('candidates.perYear', {
                      v: Number.isFinite(c.motionArcsecPerYear) ? c.motionArcsecPerYear.toFixed(1) : '—',
                    })}
                  </span>
                  {c.status !== 'artifact' && c.status !== 'rejected' && (
                    <>
                      {liveMatch?.source === 'GAIA_DR3' && (
                        <span className="tag" style={{ background: '#1d4ed8', color: '#fff' }}>
                          Gaia DR3
                        </span>
                      )}
                      {liveMatch?.source === 'SKYBOT_ASTEROID' && (
                        <span className="tag" style={{ background: '#15803d', color: '#fff' }}>
                          Asteroide
                        </span>
                      )}
                      {isPlanetXCandidate && (
                        <span className="tag" style={{ background: '#d97706', color: '#fff', fontWeight: 'bold' }}>
                          Planeta X ★
                        </span>
                      )}
                      {!liveMatch && !isPlanetXCandidate && (
                        <span className={`tag ${isKnown ? 'tag-known' : 'tag-new'}`}>
                          {isKnown ? t('candidates.known') : t('candidates.new')}
                        </span>
                      )}
                    </>
                  )}
                  <span className="snr">
                    {t('candidates.snr')} {Number.isFinite(c.snr) ? c.snr.toFixed(1) : '—'}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/**
 * Componente SVG ultra-ligero para graficar el espectro de 102 bandas de SPHEREx
 * destacando la banda clave de absorción de Metano CH4 (3.3 µm).
 */
export function SpectralSedMiniChart({ fluxes }: { fluxes: { um: number; mjy: number }[] }) {
  if (!fluxes.length) return null
  const maxFlux = Math.max(...fluxes.map((f) => f.mjy), 1)
  const minFlux = Math.min(...fluxes.map((f) => f.mjy), 0)
  const range = maxFlux - minFlux || 1

  const points = fluxes
    .map((f) => {
      const x = ((f.um - 0.75) / (5.0 - 0.75)) * 260 + 10
      const y = 70 - ((f.mjy - minFlux) / range) * 55
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <div style={{ background: '#0b1021', padding: '10px', borderRadius: '8px', marginTop: '12px', border: '1px solid #1e293b' }}>
      <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
        <span>Firma Espectral SPHEREx (102 Canales: 0.75 μm – 5.0 μm)</span>
        <span style={{ color: '#38bdf8' }}>CH₄ @ 3.3μm</span>
      </div>
      <svg width="280" height="85" viewBox="0 0 280 85" style={{ display: 'block', overflow: 'visible' }}>
        {/* Banda de absorción de Metano CH4 (3.3 um) típica de Enanas Marrones / Planeta X */}
        <rect x="165" y="10" width="18" height="65" fill="rgba(56, 189, 248, 0.2)" rx="2" />
        <line x1="174" y1="10" x2="174" y2="75" stroke="#38bdf8" strokeDasharray="2,2" strokeWidth="1" />
        <text x="174" y="22" fill="#38bdf8" fontSize="8" textAnchor="middle" fontWeight="bold">
          CH₄ (3.3μm)
        </text>

        {/* Ejes de longitud de onda */}
        <line x1="10" y1="72" x2="270" y2="72" stroke="#334155" strokeWidth="1" />
        <text x="10" y="82" fill="#64748b" fontSize="8">0.75μm</text>
        <text x="270" y="82" fill="#64748b" fontSize="8" textAnchor="end">5.0μm</text>

        {/* Curva espectral del candidato */}
        <polyline fill="none" stroke="#f59e0b" strokeWidth="2.2" points={points} />
      </svg>
    </div>
  )
}

interface DetailsProps {
  candidate: Candidate | null
  knownMatch: KnownObject | null
  liveCatalogMatch?: KnownCatalogObject | null
}

export function CandidateDetails({ candidate, knownMatch, liveCatalogMatch }: DetailsProps) {
  const { t } = useI18n()
  const [sedFluxes, setSedFluxes] = useState<{ um: number; mjy: number }[]>([])

  // Carga automática del espectro SED de 102 bandas al seleccionar candidato
  useEffect(() => {
    if (!candidate || !Number.isFinite(candidate.ra) || !Number.isFinite(candidate.dec)) {
      setSedFluxes([])
      return
    }

    let active = true
    const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
    fetch(`${apiUrl}/api/v1/sed?ra=${candidate.ra}&dec=${candidate.dec}`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (active && Array.isArray(data) && data.length > 0) {
          setSedFluxes(data)
        } else if (active) {
          // Sin fallback sintético inventado: si no hay datos reales en la API, queda vacío
          setSedFluxes([])
        }
      })
      .catch(() => {
        if (active) setSedFluxes([])
      })

    return () => {
      active = false
    }
  }, [candidate?.id, candidate?.ra, candidate?.dec])

  if (!candidate) {
    return (
      <section className="panel grow">
        <h2 className="panel-title">{t('candidates.detailsTitle')}</h2>
        <p className="muted small">{t('candidates.selectHint')}</p>
      </section>
    )
  }

  const isGaia = liveCatalogMatch?.source === 'GAIA_DR3'
  const isSkybot = liveCatalogMatch?.source === 'SKYBOT_ASTEROID'
  const isNeossat = liveCatalogMatch?.source === 'NEOSSAT_CADC'
  const isKnown = Boolean(knownMatch || isGaia || isSkybot)
  const isGoldCandidate = !isKnown && candidate.snr >= 4.5

  return (
    <section className="panel grow">
      <h2 className="panel-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>{candidate.id}</span>
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
        <dd style={{ fontWeight: 'bold', color: candidate.snr >= 5 ? '#38bdf8' : 'inherit' }}>
          {Number.isFinite(candidate.snr) ? candidate.snr.toFixed(1) : '—'}
        </dd>
      </dl>

      {/* Dictamen de Clasificación Cruzada en Vivo */}
      {candidate.status !== 'artifact' && (
        <div style={{ marginTop: '10px' }}>
          {isGaia && (
            <div className="verdict known small" style={{ borderLeft: '4px solid #1d4ed8', background: 'rgba(29, 78, 216, 0.15)', padding: '8px', borderRadius: '4px' }}>
              <strong>⭐ Estrella Conocida (Gaia DR3)</strong>
              <div className="muted">{liveCatalogMatch?.id}</div>
              {liveCatalogMatch?.infoUrl && (
                <a href={liveCatalogMatch.infoUrl} target="_blank" rel="noreferrer">
                  Ver en SIMBAD ↗
                </a>
              )}
            </div>
          )}

          {isSkybot && (
            <div className="verdict known small" style={{ borderLeft: '4px solid #16a34a', background: 'rgba(22, 163, 74, 0.15)', padding: '8px', borderRadius: '4px' }}>
              <strong>☄ Asteroide Confirmado (SkyBoT / IMCCE)</strong>
              <div className="muted">{liveCatalogMatch?.id}</div>
              {liveCatalogMatch?.infoUrl && (
                <a href={liveCatalogMatch.infoUrl} target="_blank" rel="noreferrer">
                  Ver en JPL Small-Body Database ↗
                </a>
              )}
            </div>
          )}

          {isNeossat && (
            <div className="verdict known small" style={{ borderLeft: '4px solid #06b6d4', background: 'rgba(6, 182, 212, 0.15)', padding: '8px', borderRadius: '4px', marginTop: '4px' }}>
              <strong>🛰 Observado por Telescopio Espacial NEOSSat</strong>
              <div className="muted">{liveCatalogMatch?.id}</div>
            </div>
          )}

          {isGoldCandidate && (
            <div className="verdict new small" style={{ borderLeft: '4px solid #f59e0b', background: 'rgba(245, 158, 11, 0.15)', padding: '8px', borderRadius: '4px' }}>
              <strong style={{ color: '#fbbf24' }}>★ ¡Candidato Fuerte a Enana Marrón / Planeta X!</strong>
              <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#cbd5e1' }}>
                Alto SNR en SPHEREx (IR), sin contraparte óptica en Gaia DR3 ni asteroide en SkyBoT.
              </p>
            </div>
          )}

          {!isGaia && !isSkybot && !isGoldCandidate && (
            <div className="verdict new small">
              <strong>🚀 {t('candidates.notInCatalogs')}</strong>
            </div>
          )}
        </div>
      )}

      {/* Mini-Gráfico de Firma Espectral SED (102 Bandas) */}
      <SpectralSedMiniChart fluxes={sedFluxes} />

      {Number.isFinite(candidate.ra) && Number.isFinite(candidate.dec) && (
        <div className="row gap wrap" style={{ marginTop: '12px' }}>
          <a className="chip" href={simbadUrl(candidate.ra, candidate.dec)} target="_blank" rel="noreferrer">
            SIMBAD ↗
          </a>
        </div>
      )}
    </section>
  )
}
