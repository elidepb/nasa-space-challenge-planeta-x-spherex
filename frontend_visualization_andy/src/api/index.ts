import { createHttpApi } from './httpApi'
import { createMockApi, type MockScenario } from './mockApi'
import type { SpherexApi } from './types'

const MODE_KEY = 'spherex_api_mode'

function resolveApiMode(): 'mock' | 'http' {
  try {
    const stored = localStorage.getItem(MODE_KEY)
    if (stored === 'mock' || stored === 'http') return stored
  } catch {
    // SSR / private mode
  }
  return import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock'
}

export const API_MODE: 'mock' | 'http' = resolveApiMode()

/** Cambia mock ↔ http y recarga. Sirve para el video de demo sin tocar .env. */
export function setApiMode(mode: 'mock' | 'http') {
  try {
    localStorage.setItem(MODE_KEY, mode)
  } catch {
    // ignore
  }
  window.location.reload()
}

let mockScenario: MockScenario = 'normal'
export const setMockScenario = (s: MockScenario) => {
  mockScenario = s
}

export const api: SpherexApi =
  API_MODE === 'http'
    ? createHttpApi(import.meta.env.VITE_API_URL ?? 'http://localhost:8000')
    : createMockApi(() => mockScenario)

export type { MockScenario }
export { ApiError } from './types'
