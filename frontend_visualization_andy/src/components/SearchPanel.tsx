import { useEffect, useState, type FormEvent } from 'react'
import { API_MODE, setMockScenario, type MockScenario } from '../api'
import type { MessageKey } from '../i18n'
import { useI18n } from '../i18n/I18nProvider'
import {
  CHALLENGE_TARGETS,
  DEFAULT_BAND_INDEX,
  normalizeBands,
  primaryFromBands,
} from '../lib/spectral'
import type { RegionQuery } from '../types/contracts'
import { SpectralBandPicker } from './SpectralBandPicker'

const SCENARIOS: MockScenario[] = ['normal', 'slow', 'empty', 'error']

type FieldError = 'ra' | 'dec' | 'size'

interface Props {
  busy: boolean
  onSubmit: (query: RegionQuery) => void
  /** Consulta lanzada desde fuera (URL compartida, intro) para reflejarla en el formulario. */
  externalQuery: RegionQuery | null
}

function bandsFromQuery(q: RegionQuery): number[] {
  return normalizeBands(q.bands, q.bandpass, q.group)
}

export function SearchPanel({ busy, onSubmit, externalQuery }: Props) {
  const { t } = useI18n()
  const [ra, setRa] = useState(String(CHALLENGE_TARGETS[0].query.ra))
  const [dec, setDec] = useState(String(CHALLENGE_TARGETS[0].query.dec))
  const [size, setSize] = useState(String(CHALLENGE_TARGETS[0].query.size))
  const [qr, setQr] = useState('qr2')
  const [bands, setBands] = useState<number[]>([DEFAULT_BAND_INDEX])
  const [scenario, setScenario] = useState<MockScenario>('normal')
  const [error, setError] = useState<FieldError | null>(null)

  useEffect(() => {
    if (!externalQuery) return
    setRa(String(externalQuery.ra))
    setDec(String(externalQuery.dec))
    setSize(String(externalQuery.size))
    if (externalQuery.qr) setQr(externalQuery.qr)
    setBands(bandsFromQuery(externalQuery))
  }, [externalQuery])

  function submit(e: FormEvent) {
    e.preventDefault()
    const selected = normalizeBands(bands)
    const primary = primaryFromBands(selected)
    const q: RegionQuery = {
      ra: Number(ra),
      dec: Number(dec),
      size: Number(size),
      qr,
      bandpass: primary.bandpass,
      group: primary.group,
      bands: selected,
    }
    if (!Number.isFinite(q.ra) || q.ra < 0 || q.ra >= 360) return setError('ra')
    if (!Number.isFinite(q.dec) || q.dec < -90 || q.dec > 90) return setError('dec')
    if (!Number.isFinite(q.size) || q.size <= 0 || q.size > 1) return setError('size')
    setError(null)
    onSubmit(q)
  }

  function applyPreset(q: RegionQuery) {
    setRa(String(q.ra))
    setDec(String(q.dec))
    setSize(String(q.size))
    setBands(bandsFromQuery(q))
  }

  return (
    <form className="panel search" onSubmit={submit}>
      <h2 className="panel-title">{t('search.title')}</h2>
      <div className="field-row">
        <label className="field">
          <span>{t('search.ra')}</span>
          <input value={ra} onChange={(e) => setRa(e.target.value)} inputMode="decimal" />
        </label>
        <label className="field">
          <span>{t('search.dec')}</span>
          <input value={dec} onChange={(e) => setDec(e.target.value)} inputMode="decimal" />
        </label>
      </div>
      <div className="field-row">
        <label className="field">
          <span>{t('search.size')}</span>
          <input value={size} onChange={(e) => setSize(e.target.value)} inputMode="decimal" />
        </label>
        <label className="field">
          <span>{t('search.release')}</span>
          <select value={qr} onChange={(e) => setQr(e.target.value)}>
            <option value="qr2">QR2</option>
            <option value="qr3">QR3</option>
          </select>
        </label>
      </div>

      <SpectralBandPicker selected={bands} disabled={busy} onChange={setBands} />

      <div className="presets-block">
        <span className="presets-label">{t('search.challengeTargets')}</span>
        <div className="presets">
          {CHALLENGE_TARGETS.map((p) => (
            <button
              type="button"
              key={p.id}
              className="chip challenge"
              title={`${p.query.ra.toFixed(4)}°, ${p.query.dec.toFixed(4)}° · ${p.query.bandpass} · g${p.query.group}`}
              onClick={() => applyPreset(p.query)}
            >
              {t(p.labelKey as MessageKey)}
            </button>
          ))}
        </div>
      </div>

      {API_MODE === 'mock' && (
        <label className="field">
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

      {error && <p className="form-error">{t(`search.errors.${error}`)}</p>}
      <button type="submit" className="btn primary block" disabled={busy}>
        {busy ? t('search.submitting') : t('search.submit')}
      </button>
    </form>
  )
}
