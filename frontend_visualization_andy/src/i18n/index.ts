import en, { type Messages } from './locales/en'
import es from './locales/es'

/** To add a language: create `locales/<code>.ts` typed as `Messages` and register it here. */
export const LOCALES = { en, es } satisfies Record<string, Messages>

export type Locale = keyof typeof LOCALES
export const DEFAULT_LOCALE: Locale = 'en'
const STORAGE_KEY = 'spherex.locale'

type Leaves<T, P extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Leaves<T[K], `${P}${K}.`>
}[keyof T & string]

export type MessageKey = Leaves<Messages>
export type MessageParams = Record<string, string | number>

export const isLocale = (value: unknown): value is Locale =>
  typeof value === 'string' && Object.hasOwn(LOCALES, value)

function initialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isLocale(stored)) return stored
  } catch {
    // localStorage no disponible
  }
  return DEFAULT_LOCALE
}

let current: Locale = initialLocale()

export const getLocale = () => current

export function setCurrentLocale(locale: Locale) {
  current = locale
  document.documentElement.lang = LOCALES[locale].meta.htmlLang
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // localStorage no disponible
  }
}

function lookup(messages: Messages, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], messages)
  return typeof value === 'string' ? value : undefined
}

export function translate(key: MessageKey, params?: MessageParams, locale: Locale = current): string {
  const template = lookup(LOCALES[locale], key) ?? lookup(LOCALES[DEFAULT_LOCALE], key) ?? key
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in params ? String(params[name]) : match))
}
