/**
 * Módulo de validación espacial, temporal y cinemática para candidatos del Planeta X.
 *
 * Desacopla la extracción bruta de detecciones de la decisión astronómica final.
 */

export interface Detection {
  id: string
  epoch: number
  timestampMjd: number
  ra: number
  dec: number
  snr: number // compatibilidad
  snrLocal: number // SNR con sustracción de fondo local
  isKnown: boolean
  isArtifact: boolean
  trackletId?: string
}

export type CandidateClassificationStatus =
  | 'KNOWN_CATALOG'
  | 'INSUFFICIENT_EPOCHS'
  | 'STATIC_OR_NOISY_FIT'
  | 'FAST_SOLAR_SYSTEM'
  | 'KINEMATIC_CANDIDATE'
  | 'PLANET_X_CANDIDATE'

export interface TrackletEvaluation {
  trackletId: string
  status: 'INSUFFICIENT_EPOCHS' | 'STATIC_OR_NOISY_FIT' | 'FAST_SOLAR_SYSTEM' | 'KINEMATIC_CANDIDATE'
  score: number
  residualArcsec?: number
}

export interface ClassifiedDetection extends Detection {
  status: CandidateClassificationStatus
  score: number
  residualArcsec?: number
  isPlanetXCandidate: boolean
}

/**
 * Deduplica detecciones espaciales dentro de la misma época usando supresión no máxima.
 * Si dos picos están a menos de minSepArcsec, se descarta o fusiona el de menor SNR local.
 */
export function deduplicateDetectionsInEpoch(
  detections: Detection[],
  minSepArcsec = 6.2 // 1x píxel scale típico (~FWHM)
): Detection[] {
  const byEpoch = new Map<number, Detection[]>()
  for (const d of detections) {
    if (!byEpoch.has(d.epoch)) byEpoch.set(d.epoch, [])
    byEpoch.get(d.epoch)!.push(d)
  }

  const accepted: Detection[] = []

  for (const [, epochDets] of byEpoch.entries()) {
    // Ordenar de mayor a menor snrLocal
    epochDets.sort((a, b) => b.snrLocal - a.snrLocal)

    const keep: Detection[] = []
    for (const d of epochDets) {
      let isDuplicate = false
      for (const k of keep) {
        const dra = (d.ra - k.ra) * Math.cos(((d.dec + k.dec) * Math.PI) / 360) * 3600
        const ddec = (d.dec - k.dec) * 3600
        const distArcsec = Math.hypot(dra, ddec)

        if (distArcsec < minSepArcsec) {
          isDuplicate = true
          break
        }
      }
      if (!isDuplicate) {
        keep.push(d)
      }
    }
    accepted.push(...keep)
  }

  return accepted
}

/**
 * Clasifica un lote de detecciones encadenando evaluación cinemática y selección única.
 * Promueve a PLANET_X_CANDIDATE como máximo al mejor tracklet (argmax(score)) que supere minScore.
 */
export function classifyBatch(
  detections: Detection[],
  evaluationsByTracklet: Record<string, TrackletEvaluation>,
  minScore = 0.7
): ClassifiedDetection[] {
  // 1. Clasificación individual usando SNR local + resultado cinemático
  const classified: ClassifiedDetection[] = detections.map((d) => {
    if (d.isKnown) {
      return { ...d, status: 'KNOWN_CATALOG', score: 0, isPlanetXCandidate: false }
    }

    if (d.isArtifact || d.snrLocal < 4.5 || !d.trackletId) {
      return {
        ...d,
        status: 'INSUFFICIENT_EPOCHS',
        score: 0,
        isPlanetXCandidate: false,
      }
    }

    const ev = evaluationsByTracklet[d.trackletId]
    if (!ev || ev.status !== 'KINEMATIC_CANDIDATE') {
      return {
        ...d,
        status: ev?.status ?? 'INSUFFICIENT_EPOCHS',
        score: ev?.score ?? 0,
        residualArcsec: ev?.residualArcsec,
        isPlanetXCandidate: false,
      }
    }

    return {
      ...d,
      status: 'KINEMATIC_CANDIDATE',
      score: ev.score,
      residualArcsec: ev.residualArcsec,
      isPlanetXCandidate: false,
    }
  })

  // 2. Selección global: solo el mejor tracklet pasa a PLANET_X_CANDIDATE
  const bestCandidate = classified
    .filter((item) => item.status === 'KINEMATIC_CANDIDATE' && item.score >= minScore)
    .sort((a, b) => b.score - a.score)[0]

  if (bestCandidate) {
    for (const item of classified) {
      if (item.trackletId === bestCandidate.trackletId) {
        item.status = 'PLANET_X_CANDIDATE'
        item.isPlanetXCandidate = true
      }
    }
  }

  return classified
}
