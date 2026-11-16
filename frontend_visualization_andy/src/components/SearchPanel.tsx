import { useEffect, useState, type FormEvent } from 'react'
import { API_MODE, setMockScenario, type MockScenario } from '../api'
import type { MessageKey } from '../i18n'
import { useI18n } from '../i18n/I18nProvider'
import {
  CHALLENGE_TARGETS,
  normalizeBands,
  primaryFromBands,
} from '../lib/spectral'
import type { RegionQuery } from '../types/contracts'

const SCENARIOS: MockScenario[] = ['normal', 'slow', 'empty', 'error']

type FieldError = 'ra' | 'dec' | 'size'

interface Props {
  busy: boolean
  bands: number[]
  onBandsChange: (bands: number[]) => void
  onSubmit: (query: RegionQuery) => void
  /** Consulta lanzada desde fuera (URL compartida, intro) para reflejarla en el formulario. */
  externalQuery: RegionQuery | null
  onOpenMenu?: () => void
  onBackHome?: () => void
}

function bandsFromQuery(q: RegionQuery): number[] {
  return normalizeBands(q.bands, q.bandpass, q.group)
}

export function SearchPanel({ busy, bands, onBandsChange, onSubmit, externalQuery, onOpenMenu, onBackHome }: Props) {
  const { t } = useI18n()
  const defaultTarget = CHALLENGE_TARGETS[CHALLENGE_TARGETS.length - 1]
  const [ra, setRa] = useState(String(defaultTarget.query.ra))
  const [dec, setDec] = useState(String(defaultTarget.query.dec))
  const [size, setSize] = useState(String(defaultTarget.query.size))
  const [qr, setQr] = useState('qr2')
  const [scenario, setScenario] = useState<MockScenario>('normal')
  const [error, setError] = useState<FieldError | null>(null)
  const [selectedTargetId, setSelectedTargetId] = useState<string>(defaultTarget.id)

  useEffect(() => {
    if (!externalQuery) return
    setRa(String(externalQuery.ra))
    setDec(String(externalQuery.dec))
    setSize(String(externalQuery.size))
    if (externalQuery.qr) setQr(externalQuery.qr)
    const matchedPreset = CHALLENGE_TARGETS.find(
      (p) => Math.abs(p.query.ra - externalQuery.ra) < 0.001 && Math.abs(p.query.dec - externalQuery.dec) < 0.001
    )
    if (matchedPreset) {
      setSelectedTargetId(matchedPreset.id)
    }
  }, [externalQuery])

  function submit(e: FormEvent) {
    e.preventDefault()
    const parsedRa = parseFloat(ra)
    const parsedDec = parseFloat(dec)
    const parsedSize = parseFloat(size)
    if (Number.isNaN(parsedRa) || parsedRa < 0 || parsedRa > 360) return setError('ra')
    if (Number.isNaN(parsedDec) || parsedDec < -90 || parsedDec > 90) return setError('dec')
    if (Number.isNaN(parsedSize) || parsedSize <= 0 || parsedSize > 10) return setError('size')
    setError(null)
    const primary = primaryFromBands(bands)
    const q: RegionQuery = {
      ra: parsedRa,
      dec: parsedDec,
      size: parsedSize,
      qr,
      bandpass: primary.bandpass,
      group: primary.group,
      bands,
    }
    onSubmit(q)
  }

  function applyPreset(q: RegionQuery, id: string) {
    setRa(String(q.ra))
    setDec(String(q.dec))
    setSize(String(q.size))
    setSelectedTargetId(id)
    const newBands = bandsFromQuery(q)
    onBandsChange(newBands)
    const primary = primaryFromBands(newBands)
    setError(null)
    onSubmit({
      ...q,
      bands: newBands,
      bandpass: primary.bandpass,
      group: primary.group,
    })
  }

  return (
    <form className="panel search-horizontal" onSubmit={submit}>
      <div className="search-row-top">
        <div className="search-title-block">
          {onOpenMenu && (
            <button
              type="button"
              className="menu-trigger-btn"
              onClick={onOpenMenu}
              title="Menú Principal"
              aria-label="Menú Principal"
            >
              ☰
            </button>
          )}
          <button
            type="button"
            className="brand brand-btn inline-brand"
            onClick={onBackHome}
            title={t('home.backHome')}
          >
            <img className="logo-img" src="/team-logo.jpg" alt="" width={32} height={32} />
            <div>
              <h1 className="search-app-title">{t('app.title')}</h1>
              <p className="search-app-sub muted small">{t('app.subtitle')}</p>
            </div>
          </button>
        </div>

        <div className="search-fields-inline">
          <label className="field-compact">
            <span>{t('search.ra')}</span>
            <input value={ra} onChange={(e) => setRa(e.target.value)} inputMode="decimal" />
          </label>
          <label className="field-compact">
            <span>{t('search.dec')}</span>
            <input value={dec} onChange={(e) => setDec(e.target.value)} inputMode="decimal" />
          </label>
          <label className="field-compact">
            <span>{t('search.size')}</span>
            <input value={size} onChange={(e) => setSize(e.target.value)} inputMode="decimal" />
          </label>
          <label className="field-compact">
            <span>{t('search.release')}</span>
            <select value={qr} onChange={(e) => setQr(e.target.value)}>
              <option value="qr2">QR2</option>
              <option value="qr3">QR3</option>
            </select>
          </label>

          {API_MODE === 'mock' && (
            <label className="field-compact">
              <span>{t('search.scenario')}</span>
              <select
                value={scenario}
                onChange={(e) => {
                  const s = e.target.value as MockScenario
                  setScenario(s)
                  setMockScenario(s)
                }}
              >
                {SCENARIOS.map((s) => (
                  <option key={s} value={s}>
                    {t(`search.scenarios.${s}`)}
                  </option>
                ))}
              </select>
            </label>
          )}

          <button type="submit" className="btn primary search-submit-btn" disabled={busy}>
            {busy ? t('search.submitting') : t('search.submit')}
          </button>
        </div>
      </div>

      <div className="search-row-targets">
        <span className="presets-label">{t('search.challengeTargets')}</span>
        <div className="presets-chips-row">
          {CHALLENGE_TARGETS.map((p) => (
            <button
              type="button"
              key={p.id}
              className={`chip challenge ${selectedTargetId === p.id ? 'active' : ''}`}
              title={`${p.query.ra.toFixed(4)}°, ${p.query.dec.toFixed(4)}° · ${p.query.bandpass} · g${p.query.group}`}
              onClick={() => applyPreset(p.query, p.id)}
            >
              {t(p.labelKey as MessageKey)}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="form-error">{t(`search.errors.${error}`)}</p>}
    </form>
  )
}
