import { useI18n } from '../i18n/I18nProvider'
import { LanguageSelector } from './LanguageSelector'

interface Props {
  onEnter: () => void
}

export function HomePage({ onEnter }: Props) {
  const { t } = useI18n()

  return (
    <div className="home">
      <div className="home-veil" aria-hidden />
      <header className="home-top">
        <LanguageSelector />
      </header>

      <main className="home-hero">
        <img
          className="home-logo"
          src="/team-logo.jpg"
          alt={t('home.teamName')}
          width={220}
          height={220}
        />
        <p className="home-brand">{t('home.teamName')}</p>
        <h1 className="home-title">{t('home.headline')}</h1>
        <p className="home-lead">{t('home.lead')}</p>
        <div className="home-cta">
          <button type="button" className="home-enter" onClick={onEnter}>
            {t('home.enter')}
          </button>
        </div>
      </main>
    </div>
  )
}
