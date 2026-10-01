import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  getLocale,
  LOCALES,
  setCurrentLocale,
  translate,
  type Locale,
  type MessageKey,
  type MessageParams,
} from '.'

interface I18nContextValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: MessageKey, params?: MessageParams) => string
  locales: { code: Locale; name: string }[]
}

const I18nContext = createContext<I18nContextValue | null>(null)

const AVAILABLE = (Object.keys(LOCALES) as Locale[]).map((code) => ({ code, name: LOCALES[code].meta.name }))

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getLocale)

  useEffect(() => {
    setCurrentLocale(locale)
    document.title = translate('app.title', undefined, locale)
  }, [locale])

  const setLocale = useCallback((next: Locale) => {
    setCurrentLocale(next)
    setLocaleState(next)
  }, [])

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key, params) => translate(key, params, locale),
      locales: AVAILABLE,
    }),
    [locale, setLocale],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}
