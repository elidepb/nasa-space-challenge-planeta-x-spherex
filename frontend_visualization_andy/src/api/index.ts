import { createHttpApi } from './httpApi'
import { createMockApi, type MockScenario } from './mockApi'
import type { SpherexApi } from './types'

export const API_MODE: 'mock' | 'http' = import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock'

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
