import { useEffect, useState, type FormEvent } from 'react'
import { API_MODE, setMockScenario, type MockScenario } from '../api'
import type { MessageKey } from '../i18n'
import { useI18n } from '../i18n/I18nProvider'
import {
  CHALLENGE_TARGETS,
  clampSpectralGroup,
  DEFAULT_BANDPASS,
  DEFAULT_SPECTRAL_GROUP,
  normalizeBandpass,
  SPECTRAL_FEATURES,
  type Bandpass,
  type SpectralFeatureId,
} from '../lib/spectral'
import type { RegionQuery } from '../types/contracts'
import { SpectralBandRuler } from './SpectralBandRuler'

const DEMO_PRESETS: { label: MessageKey; query: RegionQuery }[] = [
  { label: 'search.presets.m101', query: { ra: 210.80227, dec: 54.34895, size: 0.05 } },
  { label: 'search.presets.nep', query: { ra: 270.0, dec: 66.56071, size: 0.05 } },
  { label: 'search.presets.sep', query: { ra: 90.0, dec: -66.56071, size: 0.05 } },
]

const SCENARIOS: MockScenario[] = ['normal', 'slow', 'empty', 'error']

type FieldError = 'ra' | 'dec' | 'size'

interface Props {
  busy: boolean
  onSubmit: (query: RegionQuery) => void
  /** Consulta lanzada desde fuera (URL compartida, intro) para reflejarla en el formulario. */
  externalQuery: RegionQuery | null
  /** Capas IR activas en el visor. */
  activeFeatures: SpectralFeatureId[]
  /** Hay capas disponibles (tras un análisis). */
  layersAvailable: boolean
  onToggleFeature: (id: SpectralFeatureId) => void
}

export function SearchPanel({
  busy,
  onSubmit,
  externalQuery,
  activeFeatures,
  layersAvailable,
  onToggleFeature,
}: Props) {
  const { t } = useI18n()
  const [ra, setRa] = useState('210.80227')
  const [dec, setDec] = useState('54.34895')
  const [size, setSize] = useState('0.05')
  const [qr, setQr] = useState('qr2')
  const [bandpass, setBandpass] = useState<Bandpass>(DEFAULT_BANDPASS)
  const [group, setGroup] = useState(DEFAULT_SPECTRAL_GROUP)
  const [scenario, setScenario] = useState<MockScenario>('normal')
  const [error, setError] = useState<FieldError | null>(null)

  useEffect(() => {
    if (!externalQuery) return
    setRa(String(externalQuery.ra))
    setDec(String(externalQuery.dec))
    setSize(String(externalQuery.size))
    if (externalQuery.qr) setQr(externalQuery.qr)
    if (externalQuery.bandpass) setBandpass(normalizeBandpass(externalQuery.bandpass))
    if (externalQuery.group != null) setGroup(clampSpectralGroup(externalQuery.group))
  }, [externalQuery])

  function submit(e: FormEvent) {
    e.preventDefault()
    const q: RegionQuery = {
      ra: Number(ra),
      dec: Number(dec),
      size: Number(size),
      qr,
      bandpass,
      group: clampSpectralGroup(group),
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
    if (q.bandpass) setBandpass(normalizeBandpass(q.bandpass))
    if (q.group != null) setGroup(clampSpectralGroup(q.group))
  }

  function toggleFeature(id: SpectralFeatureId) {
    const feat = SPECTRAL_FEATURES.find((f) => f.id === id)
    const turningOn = !activeFeatures.includes(id)
    if (turningOn && feat) {
      setBandpass(feat.bandpass)
      setGroup(feat.group)
    }
    onToggleFeature(id)
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

      <SpectralBandRuler
        bandpass={bandpass}
        group={group}
        disabled={busy}
        onBandpassChange={setBandpass}
        onGroupChange={setGroup}
      />

      <div className="feature-layers" role="group" aria-label={t('search.layersTitle')}>
        <div className="feature-layers-head">
          <span className="feature-jumps-label">{t('search.layersTitle')}</span>
          <p className="muted small" style={{ margin: 0 }}>
            {layersAvailable ? t('search.layersHint') : t('search.layersNeedAnalysis')}
          </p>
        </div>
        <div className="feature-jumps">
          {SPECTRAL_FEATURES.map((f) => {
            const on = activeFeatures.includes(f.id)
            return (
              <button
                key={f.id}
                type="button"
                className={`chip feature-chip feature-${f.id} ${on ? 'active' : ''}`}
                disabled={!layersAvailable}
                aria-pressed={on}
                title={t(`search.features.${f.id}Hint`)}
                onClick={() => toggleFeature(f.id)}
              >
                {on ? '✓ ' : ''}
                {t(`search.features.${f.id}`)}
              </button>
            )
          })}
        </div>
      </div>

      <div className="presets-block">
        <span className="presets-label">{t('search.challengeTargets')}</span>
        <div className="presets">
          {CHALLENGE_TARGETS.map((p) => (
            <button
              type="button"
              key={p.id}
              className="chip challenge"
              title={`${p.query.ra.toFixed(4)}°, ${p.query.dec.toFixed(4)}°`}
              onClick={() => applyPreset(p.query)}
            >
              {t(p.labelKey as MessageKey)}
            </button>
          ))}
        </div>
      </div>

      <div className="presets-block">
        <span className="presets-label">{t('search.demoTargets')}</span>
        <div className="presets">
          {DEMO_PRESETS.map((p) => (
            <button type="button" key={p.label} className="chip" onClick={() => applyPreset(p.query)}>
              {t(p.label)}
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
