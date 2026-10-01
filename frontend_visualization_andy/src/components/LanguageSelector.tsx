import { isLocale } from '../i18n'
import { useI18n } from '../i18n/I18nProvider'

export function LanguageSelector() {
  const { locale, setLocale, locales, t } = useI18n()
  return (
    <label className="lang-select" title={t('app.language')}>
      <span aria-hidden>🌐</span>
      <select
        aria-label={t('app.language')}
        value={locale}
        onChange={(e) => isLocale(e.target.value) && setLocale(e.target.value)}
      >
        {locales.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </select>
    </label>
  )
}
