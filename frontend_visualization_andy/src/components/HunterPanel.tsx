import { useEffect, useMemo, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import {
  bestMatch,
  computeMotion,
  sbdbUrl,
  simbadUrl,
  sortMarks,
  type HunterMark,
} from '../lib/hunter'
import { formatDecDms, formatRaHms, formatTimestamp } from '../lib/sky'
import type { AnalysisImages, Candidate, KnownObject, ObservationSummary, RegionQuery } from '../types/contracts'

interface Props {
  observations: ObservationSummary[]
  marks: HunterMark[]
  region: RegionQuery
  images: AnalysisImages
  knownObjects: KnownObject[]
  candidates: Candidate[]
  activeObservationId: string | null
  autoAdvance: boolean
  onAutoAdvance: (v: boolean) => void
  onRemoveMark: (observationId: string) => void
  onClear: () => void
  onSelectObservation: (index: number) => void
  onSelectCandidate: (id: string) => void
  onExit: () => void
  onToast: (msg: string) => void
}

type Verdict =
  | { kind: 'known'; object: KnownObject }
  | { kind: 'candidate'; candidate: Candidate }
  | { kind: 'new' }

export function HunterPanel(props: Props) {
  const { t } = useI18n()
  const { observations, marks, images, region } = props
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [checking, setChecking] = useState(false)

  const sorted = useMemo(() => sortMarks(marks, observations), [marks, observations])
  const motion = useMemo(
    () => computeMotion(marks, observations, region, images.pixelScaleArcsec, images.width, images.height),
    [marks, observations, region, images],
  )
  const marked = new Set(marks.map((m) => m.observationId))

  useEffect(() => setVerdict(null), [marks])

  function verify() {
    setChecking(true)
    setVerdict(null)
    const tol = 2.5 * (images.width / 64)
    setTimeout(() => {
      const known = bestMatch(marks, props.knownObjects, (o) => o.positions, tol)
      const cand = bestMatch(marks, props.candidates, (c) => c.detections, tol)
      setVerdict(known ? { kind: 'known', object: known.item } : cand ? { kind: 'candidate', candidate: cand.item } : { kind: 'new' })
      setChecking(false)
    }, 700)
  }

  async function copyReport() {
    if (!motion) return
    const report = {
      tool: 'SPHEREx · Planet X',
      region,
      marks: sorted.map((m) => ({
        observationId: m.observationId,
        timestamp: observations.find((o) => o.id === m.observationId)?.timestamp,
        x: +m.x.toFixed(2),
        y: +m.y.toFixed(2),
      })),
      start: motion.start,
      end: motion.end,
      displacementArcsec: +motion.displacementArcsec.toFixed(2),
      motionArcsecPerYear: +motion.motionArcsecPerYear.toFixed(2),
      positionAngleDeg: +motion.positionAngleDeg.toFixed(1),
      verdict: verdict?.kind ?? 'unchecked',
    }
    await navigator.clipboard?.writeText(JSON.stringify(report, null, 2)).catch(() => undefined)
    props.onToast(t('hunter.reportCopied'))
  }

  return (
    <section className="panel grow hunter-panel">
      <h2 className="panel-title">
        🎯 {t('hunter.title')}
        <button className="chip push-right" onClick={props.onExit}>
          {t('hunter.exit')}
        </button>
      </h2>
      <p className="muted small">{t('hunter.instructions')}</p>

      <label className="check small">
        <input type="checkbox" checked={props.autoAdvance} onChange={(e) => props.onAutoAdvance(e.target.checked)} />
        {t('hunter.autoAdvance')}
      </label>

      <div className="hunter-progress">
        <span className="mono">{t('hunter.progress', { n: marks.length, total: observations.length })}</span>
        <div className="hunter-dots">
          {observations.map((o, i) => (
            <button
              key={o.id}
              className={`hunter-dot ${marked.has(o.id) ? 'done' : ''} ${o.id === props.activeObservationId ? 'current' : ''}`}
              onClick={() => props.onSelectObservation(i)}
              title={formatTimestamp(o.timestamp)}
            >
              {i + 1}
            </button>
          ))}
        </div>
      </div>

      {marks.length === 2 && <p className="note warn small">⚠ {t('hunter.ghostWarning')}</p>}

      {motion && (
        <dl className="details">
          <dt>{t('hunter.displacement')}</dt>
          <dd>{motion.displacementArcsec.toFixed(2)}″</dd>
          <dt>{t('hunter.motion')}</dt>
          <dd>{t('candidates.perYear', { v: motion.motionArcsecPerYear.toFixed(2) })}</dd>
          <dt>{t('hunter.direction')}</dt>
          <dd>
            {t(`hunter.compass.${motion.direction}`)} ({motion.positionAngleDeg.toFixed(0)}°)
          </dd>
          <dt>{t('hunter.span')}</dt>
          <dd>{t('hunter.days', { n: motion.spanDays.toFixed(0) })}</dd>
          <dt>{t('hunter.start')}</dt>
          <dd>
            {formatRaHms(motion.start.ra)} {formatDecDms(motion.start.dec)}
          </dd>
        </dl>
      )}

      <div className="row gap">
        <button className="btn primary grow" onClick={verify} disabled={marks.length < 2 || checking}>
          {checking ? t('hunter.checking') : t('hunter.verify')}
        </button>
        <button className="btn ghost" onClick={props.onClear} disabled={marks.length === 0}>
          {t('hunter.clear')}
        </button>
      </div>

      {verdict?.kind === 'known' && (
        <div className="verdict known">
          <strong>✓ {t('hunter.verdictKnownTitle')}</strong>
          <p>
            {t('hunter.verdictKnownText', { name: verdict.object.name, type: t(`knownTypes.${verdict.object.type}`) })}
          </p>
          <a href={sbdbUrl(verdict.object.name)} target="_blank" rel="noreferrer">
            {t('hunter.openSbdb')} ↗
          </a>
        </div>
      )}
      {verdict?.kind === 'candidate' && (
        <div className="verdict candidate">
          <strong>★ {t('hunter.verdictCandidateTitle')}</strong>
          <p>{t('hunter.verdictCandidateText', { id: verdict.candidate.id })}</p>
          <button className="chip" onClick={() => props.onSelectCandidate(verdict.candidate.id)}>
            {t('hunter.showCandidate', { id: verdict.candidate.id })}
          </button>
        </div>
      )}
      {verdict?.kind === 'new' && (
        <div className="verdict new">
          <strong>🚀 {t('hunter.verdictNewTitle')}</strong>
          <p>{t('hunter.verdictNewText')}</p>
        </div>
      )}

      {motion && verdict && (
        <div className="row gap wrap">
          <a className="chip" href={simbadUrl(motion.start.ra, motion.start.dec)} target="_blank" rel="noreferrer">
            SIMBAD ↗
          </a>
          <button className="chip" onClick={copyReport}>
            {t('hunter.copyReport')}
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <table className="det-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{t('candidates.table.date')}</th>
              <th>{t('candidates.table.position')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => {
              const idx = observations.findIndex((o) => o.id === m.observationId)
              return (
                <tr key={m.observationId} className={m.observationId === props.activeObservationId ? 'active' : ''} onClick={() => props.onSelectObservation(idx)}>
                  <td>{idx + 1}</td>
                  <td>{formatTimestamp(observations[idx].timestamp).slice(0, 10)}</td>
                  <td>
                    {m.x.toFixed(1)}, {m.y.toFixed(1)}
                  </td>
                  <td>
                    <button
                      className="link-btn"
                      onClick={(e) => {
                        e.stopPropagation()
                        props.onRemoveMark(m.observationId)
                      }}
                      title={t('hunter.removeMark')}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}
