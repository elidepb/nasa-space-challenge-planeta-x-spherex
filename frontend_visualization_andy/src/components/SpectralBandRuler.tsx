import { useMemo } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import {
  BANDPASSES,
  clampSpectralGroup,
  DETECTOR_RANGES,
  getSpectralBin,
  N_SPECTRAL_GROUPS,
  type Bandpass,
} from '../lib/spectral'

interface Props {
  bandpass: Bandpass
  group: number
  disabled?: boolean
  onBandpassChange: (bandpass: Bandpass) => void
  onGroupChange: (group: number) => void
}

export function SpectralBandRuler({ bandpass, group, disabled, onBandpassChange, onGroupChange }: Props) {
  const { t } = useI18n()
  const bin = useMemo(() => getSpectralBin(bandpass, group), [bandpass, group])
  const [detMin, detMax] = DETECTOR_RANGES[bandpass]
  const safeGroup = clampSpectralGroup(group)
  const pct = ((safeGroup - 1) / (N_SPECTRAL_GROUPS - 1)) * 100

  return (
    <div className={`spectral-ruler ${disabled ? 'disabled' : ''}`}>
      <div className="spectral-ruler-head">
        <span className="spectral-ruler-title">{t('search.spectralTitle')}</span>
        <span className="spectral-ruler-readout" title={t('search.spectralHint')}>
          {t('search.spectralReadout', {
            band: bandpass.replace('SPHEREx-', ''),
            group: safeGroup,
            lambda: bin.wlCenter.toFixed(3),
          })}
        </span>
      </div>

      <div className="spectral-band-chips" role="group" aria-label={t('search.bandpass')}>
        {BANDPASSES.map((b) => (
          <button
            key={b}
            type="button"
            className={`spectral-chip ${b === bandpass ? 'active' : ''}`}
            disabled={disabled}
            onClick={() => onBandpassChange(b)}
            title={`${b} · ${DETECTOR_RANGES[b][0].toFixed(2)}–${DETECTOR_RANGES[b][1].toFixed(2)} μm`}
          >
            {b.replace('SPHEREx-', '')}
          </button>
        ))}
      </div>

      <div className="spectral-track">
        <div className="spectral-gradient" style={{ ['--thumb' as string]: `${pct}%` }} />
        <input
          type="range"
          className="spectral-slider"
          min={1}
          max={N_SPECTRAL_GROUPS}
          step={1}
          value={safeGroup}
          disabled={disabled}
          aria-label={t('search.channel')}
          aria-valuetext={t('search.spectralReadout', {
            band: bandpass.replace('SPHEREx-', ''),
            group: safeGroup,
            lambda: bin.wlCenter.toFixed(3),
          })}
          onChange={(e) => onGroupChange(Number(e.target.value))}
        />
        <div className="spectral-ticks" aria-hidden>
          {Array.from({ length: N_SPECTRAL_GROUPS }, (_, i) => (
            <button
              key={i + 1}
              type="button"
              className={`spectral-tick ${i + 1 === safeGroup ? 'active' : ''}`}
              disabled={disabled}
              tabIndex={-1}
              onClick={() => onGroupChange(i + 1)}
            />
          ))}
        </div>
        <div className="spectral-ends">
          <span>{detMin.toFixed(2)} μm</span>
          <span>{t('search.channelOf', { n: safeGroup, total: N_SPECTRAL_GROUPS })}</span>
          <span>{detMax.toFixed(2)} μm</span>
        </div>
      </div>

      <p className="spectral-hint muted small">{t('search.spectralHint')}</p>
    </div>
  )
}
