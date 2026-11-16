import { useEffect, useState } from 'react'
import { API_MODE, setMockScenario, type MockScenario } from '../api'
import { useI18n } from '../i18n/I18nProvider'
import type { Locale, MessageKey } from '../i18n'
import { CHALLENGE_TARGETS } from '../lib/spectral'
import type { RegionQuery } from '../types/contracts'

interface Props {
  isOpen: boolean
  onClose: () => void
  onOpenModal: (name: 'intro' | 'guide' | 'help' | 'about') => void
  onSelectTarget: (query: RegionQuery, id: string) => void
}

const SCENARIOS: MockScenario[] = ['normal', 'slow', 'empty', 'error']

/* SVGs inline adaptados a la paleta del proyecto (var(--accent), cyan, azul celeste) */
function IconStory() {
  return (
    <svg className="drawer-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l2.4 6.9 7.1.6-5.3 4.8 1.6 7-5.8-3.5-5.8 3.5 1.6-7-5.3-4.8 7.1-.6z" />
    </svg>
  )
}

function IconGuide() {
  return (
    <svg className="drawer-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  )
}

function IconKeyboard() {
  return (
    <svg className="drawer-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M6 8h.001M10 8h.001M14 8h.001M18 8h.001M8 12h.001M12 12h.001M16 12h.001M7 16h10" />
    </svg>
  )
}

function IconCredits() {
  return (
    <svg className="drawer-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  )
}

function IconTargets() {
  return (
    <svg className="drawer-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  )
}

function IconSettings() {
  return (
    <svg className="drawer-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  )
}

export function NavigationDrawer({ isOpen, onClose, onOpenModal, onSelectTarget }: Props) {
  const { t, locale, setLocale } = useI18n()
  const [targetsOpen, setTargetsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [scenario, setScenario] = useState<MockScenario>('normal')

  // Cerrar con Escape
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden />
      <aside className="drawer-panel" aria-label="Menú Principal">
        {/* Cabecera del Menú */}
        <div className="drawer-header">
          <div className="drawer-header-left">
            <img src="/team-logo.jpg" alt="Logo" className="drawer-avatar" width={32} height={32} />
            <div className="drawer-header-meta">
              <span className="drawer-title">{locale === 'es' ? 'Menú Principal' : 'Main Menu'}</span>
              <span className="drawer-brand-sub">SPHEREx · Planeta X</span>
            </div>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            title={t('common.close')}
            aria-label={t('common.close')}
          >
            ✕
          </button>
        </div>

        <div className="drawer-divider" />

        {/* Lista de Navegación */}
        <nav className="drawer-nav">
          <button
            type="button"
            className="drawer-nav-item"
            onClick={() => {
              onClose()
              onOpenModal('intro')
            }}
          >
            <div className="drawer-item-left">
              <span className="drawer-item-icon"><IconStory /></span>
              <span className="drawer-item-text">{t('nav.intro')}</span>
            </div>
          </button>

          <button
            type="button"
            className="drawer-nav-item"
            onClick={() => {
              onClose()
              onOpenModal('guide')
            }}
          >
            <div className="drawer-item-left">
              <span className="drawer-item-icon"><IconGuide /></span>
              <span className="drawer-item-text">{t('nav.guide')}</span>
            </div>
          </button>

          <button
            type="button"
            className="drawer-nav-item"
            onClick={() => {
              onClose()
              onOpenModal('help')
            }}
          >
            <div className="drawer-item-left">
              <span className="drawer-item-icon"><IconKeyboard /></span>
              <span className="drawer-item-text">{t('nav.help')}</span>
            </div>
          </button>

          <button
            type="button"
            className="drawer-nav-item"
            onClick={() => {
              onClose()
              onOpenModal('about')
            }}
          >
            <div className="drawer-item-left">
              <span className="drawer-item-icon"><IconCredits /></span>
              <span className="drawer-item-text">{t('nav.about')}</span>
            </div>
          </button>

          <div className="drawer-divider" />

          {/* Submenú desplegable: Objetivos con datos SPHEREx */}
          <div className="drawer-submenu-group">
            <button
              type="button"
              className="drawer-nav-item drawer-accordion-btn"
              onClick={() => setTargetsOpen((o) => !o)}
            >
              <div className="drawer-item-left">
                <span className="drawer-item-icon"><IconTargets /></span>
                <span className="drawer-item-text">{t('search.challengeTargets')}</span>
              </div>
              <span className={`drawer-arrow ${targetsOpen ? 'open' : ''}`}>▼</span>
            </button>
            {targetsOpen && (
              <div className="drawer-submenu-list">
                {CHALLENGE_TARGETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className="drawer-subitem"
                    onClick={() => {
                      onSelectTarget(p.query, p.id)
                      onClose()
                    }}
                  >
                    <span className="drawer-subitem-bullet">•</span>
                    <span>{t(p.labelKey as MessageKey)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="drawer-divider" />

          {/* Submenú desplegable: Configuración */}
          <div className="drawer-submenu-group">
            <button
              type="button"
              className="drawer-nav-item drawer-accordion-btn"
              onClick={() => setSettingsOpen((o) => !o)}
            >
              <div className="drawer-item-left">
                <span className="drawer-item-icon"><IconSettings /></span>
                <span className="drawer-item-text">{locale === 'es' ? 'Configuración' : 'Settings'}</span>
              </div>
              <span className={`drawer-arrow ${settingsOpen ? 'open' : ''}`}>▼</span>
            </button>
            {settingsOpen && (
              <div className="drawer-submenu-list drawer-settings-panel">
                <div className="drawer-setting-row">
                  <label htmlFor="drawer-lang-select">{t('app.language')}</label>
                  <select
                    id="drawer-lang-select"
                    value={locale}
                    onChange={(e) => setLocale(e.target.value as Locale)}
                    className="drawer-select"
                  >
                    <option value="es">Español</option>
                    <option value="en">English</option>
                  </select>
                </div>
                {API_MODE === 'mock' && (
                  <div className="drawer-setting-row">
                    <label htmlFor="drawer-scenario-select">{t('search.scenario')}</label>
                    <select
                      id="drawer-scenario-select"
                      value={scenario}
                      onChange={(e) => {
                        const s = e.target.value as MockScenario
                        setScenario(s)
                        setMockScenario(s)
                      }}
                      className="drawer-select"
                    >
                      {SCENARIOS.map((s) => (
                        <option key={s} value={s}>
                          {t(`search.scenarios.${s}`)}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}
          </div>
        </nav>
      </aside>
    </>
  )
}
