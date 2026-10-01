import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import {
  COLORMAPS,
  colormapGradient,
  DEFAULT_IMAGE_SETTINGS,
  isDefaultSettings,
  STRETCHES,
  type ImageSettings,
} from '../lib/imageProcessing'

interface Props {
  settings: ImageSettings
  onChange: (s: ImageSettings) => void
  colorApplicable: boolean
}

export function ImageControls({ settings, onChange, colorApplicable }: Props) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const set = <K extends keyof ImageSettings>(k: K, v: ImageSettings[K]) => onChange({ ...settings, [k]: v })

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    window.addEventListener('pointerdown', onDown)
    return () => window.removeEventListener('pointerdown', onDown)
  }, [open])

  return (
    <div className="popover-anchor" ref={ref}>
      <button
        className={`tool-btn ${open || !isDefaultSettings(settings) ? 'active' : ''}`}
        onClick={() => setOpen((o) => !o)}
        title={t('imageControls.title')}
      >
        ◐ <span>{t('imageControls.button')}</span>
      </button>
      {open && (
        <div className="popover">
          <h3 className="subtitle">{t('imageControls.title')}</h3>
          <label className="field">
            <span>{t('imageControls.stretch')}</span>
            <select value={settings.stretch} onChange={(e) => set('stretch', e.target.value as ImageSettings['stretch'])} disabled={!colorApplicable}>
              {STRETCHES.map((s) => (
                <option key={s} value={s}>
                  {t(`imageControls.stretches.${s}`)}
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            <span>{t('imageControls.colormap')}</span>
            <div className="colormaps">
              {COLORMAPS.map((c) => (
                <button
                  key={c}
                  className={`colormap ${settings.colormap === c ? 'active' : ''}`}
                  onClick={() => set('colormap', c)}
                  disabled={!colorApplicable}
                  title={t(`imageControls.colormaps.${c}`)}
                >
                  <span className="swatch" style={{ background: colormapGradient(c) }} />
                  <span className="small">{t(`imageControls.colormaps.${c}`)}</span>
                </button>
              ))}
            </div>
          </div>
          {!colorApplicable && <p className="muted small">{t('imageControls.differenceNote')}</p>}
          <label className="field">
            <span>
              {t('imageControls.brightness')} <span className="mono">{settings.brightness.toFixed(2)}</span>
            </span>
            <input type="range" min={-0.5} max={0.5} step={0.02} value={settings.brightness} onChange={(e) => set('brightness', Number(e.target.value))} />
          </label>
          <label className="field">
            <span>
              {t('imageControls.contrast')} <span className="mono">{settings.contrast.toFixed(2)}</span>
            </span>
            <input type="range" min={0.5} max={3} step={0.05} value={settings.contrast} onChange={(e) => set('contrast', Number(e.target.value))} />
          </label>
          <label className="check">
            <input type="checkbox" checked={settings.invert} onChange={(e) => set('invert', e.target.checked)} />
            {t('imageControls.invert')}
          </label>
          <button className="btn ghost block" onClick={() => onChange(DEFAULT_IMAGE_SETTINGS)}>
            {t('imageControls.reset')}
          </button>
        </div>
      )}
    </div>
  )
}
