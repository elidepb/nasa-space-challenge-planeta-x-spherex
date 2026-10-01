import { generateSyntheticDataset, type SyntheticDataset } from '../mock/syntheticSky'
import { translate } from '../i18n'
import type { AnalysisInfo, RegionQuery } from '../types/contracts'
import { ApiError, type SpherexApi } from './types'

export type MockScenario = 'normal' | 'empty' | 'error' | 'slow'

const PENDING_MS = 500
const PROCESSING_MS = 2200

interface MockAnalysis {
  info: AnalysisInfo
  scenario: MockScenario
  startedAt: number
  dataset?: SyntheticDataset
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function createMockApi(getScenario: () => MockScenario): SpherexApi {
  const store = new Map<string, MockAnalysis>()
  let counter = 0

  function find(id: string): MockAnalysis {
    const entry = store.get(id)
    if (!entry) throw new ApiError(translate('errors.notFound', { id }), 404)
    return entry
  }

  function refresh(entry: MockAnalysis): AnalysisInfo {
    const elapsed = Date.now() - entry.startedAt
    const total = entry.scenario === 'slow' ? PROCESSING_MS * 3 : PROCESSING_MS
    if (elapsed < PENDING_MS) {
      entry.info = { ...entry.info, status: 'pending', progress: 0, message: translate('mock.queued') }
    } else if (elapsed < PENDING_MS + total) {
      const progress = (elapsed - PENDING_MS) / total
      const message =
        progress < 0.35
          ? translate('mock.querying')
          : progress < 0.7
            ? translate('mock.aligning')
            : translate('mock.detecting')
      entry.info = { ...entry.info, status: 'processing', progress, message }
    } else if (entry.scenario === 'error') {
      entry.info = {
        ...entry.info,
        status: 'error',
        progress: undefined,
        error: translate('mock.timeout'),
      }
    } else {
      entry.info = { ...entry.info, status: 'completed', progress: 1, message: translate('mock.completed') }
    }
    return entry.info
  }

  function dataset(entry: MockAnalysis): SyntheticDataset {
    if (refresh(entry).status !== 'completed') {
      throw new ApiError(translate('errors.notCompleted'), 409)
    }
    if (entry.scenario === 'empty') {
      return {
        observations: [],
        candidates: [],
        knownObjects: [],
        images: { width: 64, height: 64, pixelScaleArcsec: 6.2, epochs: [], differences: [] },
      }
    }
    entry.dataset ??= generateSyntheticDataset(entry.info.region)
    return entry.dataset
  }

  return {
    async createAnalysis(query: RegionQuery) {
      await delay(250)
      const id = `A-${String(++counter).padStart(4, '0')}`
      const entry: MockAnalysis = {
        info: { id, status: 'pending', region: query, createdAt: new Date().toISOString(), progress: 0 },
        scenario: getScenario(),
        startedAt: Date.now(),
      }
      store.set(id, entry)
      return entry.info
    },
    async getAnalysis(id) {
      await delay(120)
      return refresh(find(id))
    },
    async getObservations(id) {
      await delay(150)
      return dataset(find(id)).observations
    },
    async getCandidates(id) {
      await delay(150)
      return dataset(find(id)).candidates
    },
    async getImages(id) {
      await delay(200)
      return dataset(find(id)).images
    },
    async getKnownObjects(id) {
      await delay(180)
      return dataset(find(id)).knownObjects
    },
  }
}
