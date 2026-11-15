import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CandidateDetails, CandidateList } from './components/CandidatePanel'
import { Filmstrip } from './components/Filmstrip'
import { HomePage } from './components/HomePage'
import { ImageControls } from './components/ImageControls'
import { AboutModal, FieldGuideModal, HelpModal } from './components/InfoModals'
import { IntroModal } from './components/IntroModal'
import { LanguageSelector } from './components/LanguageSelector'
import { SearchPanel } from './components/SearchPanel'
import { SkyViewer } from './components/SkyViewer'
import { StatusView } from './components/StatusView'
import { Timeline } from './components/Timeline'
import { useAnalysis } from './hooks/useAnalysis'
import { useProcessedImage } from './hooks/useProcessedImage'
import { useI18n } from './i18n/I18nProvider'
import { exportGif, type GifFrame } from './lib/gif'
import {
  fetchGaiaHighPMStars,
  fetchKnownAsteroidsSkyBoT,
  fetchNEOSSatObservations,
  matchTrack,
  type KnownCatalogObject,
} from './lib/hunter'
import {
  cssFilterFor,
  DEFAULT_IMAGE_SETTINGS,
  isDefaultSettings,
  processImage,
  type ImageSettings,
} from './lib/imageProcessing'
import { formatTimestamp } from './lib/sky'
import { SPECTRAL_FEATURES, type SpectralFeatureId } from './lib/spectral'
import {
  readUrlState,
  useWiseViewUrlState,
  VIEW_MODES,
  writeUrlState,
  type UrlState,
  type ViewMode,
} from './lib/urlState'
import type { KnownObject, RegionQuery } from './types/contracts'

const MODE_ICON: Record<ViewMode, string> = { original: '▣', swipe: '⇔', blink: '◐' }

const SPEEDS = [
  { label: '0.5×', stepMs: 1600 },
  { label: '1×', stepMs: 800 },
  { label: '2×', stepMs: 400 },
]

const INTRO_KEY = 'spherex.introSeen'
const ENTERED_KEY = 'spherex.entered'
/** Primer target con datos verificados (WISE 0855 · D2 · canal 7). */
const DEMO_QUERY: RegionQuery = {
  ra: 133.795129,
  dec: -7.245147,
  size: 0.85,
  qr: 'qr2',
  bandpass: 'SPHEREx-D2',
  group: 7,
  bands: [24],
}

function alreadyEntered() {
  try {
    return sessionStorage.getItem(ENTERED_KEY) === '1'
  } catch {
    return false
  }
}

type ModalName = 'intro' | 'guide' | 'help' | 'about' | null

function introAlreadySeen() {
  try {
    return localStorage.getItem(INTRO_KEY) === '1'
  } catch {
    return true
  }
}

export default function App() {
  const { t } = useI18n()
  const analysis = useAnalysis()
  const { result, phase } = analysis
  const observations = result?.observations ?? []
  const candidates = result?.candidates ?? []
  const knownObjects = result?.knownObjects ?? []
  const images = result?.images

  const [initialUrl] = useState<UrlState>(readUrlState)
  const pendingView = useRef<UrlState | null>(initialUrl.query ? initialUrl : null)
  const centerRef = useRef<HTMLElement>(null)
  const [entered, setEntered] = useState(() => alreadyEntered() || Boolean(initialUrl.query))

  const [lastQuery, setLastQuery] = useState<RegionQuery | null>(null)
  const [externalQuery, setExternalQuery] = useState<RegionQuery | null>(initialUrl.query)
  const [activeIndex, setActiveIndex] = useState(0)
  const [referenceIndex, setReferenceIndex] = useState(0)
  const [mode, setMode] = useState<ViewMode>(initialUrl.mode ?? 'original')
  const [playing, setPlaying] = useState(false)
  const [speedLevel, setSpeedLevel] = useState(1)
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const [showOverlays, setShowOverlays] = useState(true)
  // Off: los puntos verdes de otras épocas se veían como “marcas sueltas” al lado del círculo.
  const [showTrajectories, setShowTrajectories] = useState(false)
  const [showKnown, setShowKnown] = useState(false)
  const [showGrid, setShowGrid] = useState(false)
  const [activeFeatures, setActiveFeatures] = useState<SpectralFeatureId[]>([])
  const [imageSettings, setImageSettings] = useState<ImageSettings>(DEFAULT_IMAGE_SETTINGS)
  const [modal, setModal] = useState<ModalName>(initialUrl.query || introAlreadySeen() ? null : 'intro')
  const [toast, setToast] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [wiseState, setWiseState] = useWiseViewUrlState()
  const [diffMode, setDiffMode] = useState<boolean>(() => wiseState.diff)
  const [pmra, setPmra] = useState<number>(() => wiseState.pmra)
  const [pmdec, setPmdec] = useState<number>(() => wiseState.pmdec)
  const [liveMatches, setLiveMatches] = useState<Map<string, KnownCatalogObject>>(new Map())

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast((cur) => (cur === msg ? null : cur)), 2200)
  }, [])

  const runSearch = useCallback(
    (q: RegionQuery) => {
      setLastQuery(q)
      analysis.start(q)
    },
    [analysis.start],
  )

  // No auto-lanzar análisis al cargar/recargar: la URL solo rellena el formulario.

  // Nuevo resultado: restablecer vista (o aplicar la de una URL compartida).
  useEffect(() => {
    if (!result) return
    const n = observations.length
    setReferenceIndex(0)
    setPlaying(false)
    const pending = pendingView.current
    pendingView.current = null
    if (pending) {
      setMode(pending.mode === 'swipe' ? 'swipe' : 'original')
      setActiveIndex(Math.min(n - 1, Math.max(0, pending.epoch ?? (n > 1 ? n - 1 : 0))))
      setSelectedCandidateId(candidates.some((c) => c.id === pending.candidate) ? pending.candidate! : null)
    } else {
      setActiveIndex(n > 1 ? n - 1 : 0)
      setSelectedCandidateId(null)
    }
  }, [result])

  useEffect(() => {
    if (!lastQuery) return
    writeUrlState({
      query: lastQuery,
      mode,
      epoch: result ? activeIndex : undefined,
      candidate: selectedCandidateId ?? undefined,
    })
  }, [lastQuery, mode, activeIndex, selectedCandidateId, result])

  useEffect(() => {
    if (!images) return
    for (const url of images.epochs.map((e) => e.url)) {
      new Image().src = url
    }
  }, [images])

  useEffect(() => {
    if (!images || isDefaultSettings(imageSettings)) return
    images.epochs.forEach((e) => void processImage(e.url, imageSettings).catch(() => undefined))
  }, [images, imageSettings])

  const step = useCallback(
    (delta: number) => {
      const n = observations.length
      if (n === 0) return
      setActiveIndex((i) => (i + delta + n) % n)
    },
    [observations.length],
  )

  const speed = SPEEDS[speedLevel] ?? SPEEDS[1]

  useEffect(() => {
    if (!playing || observations.length < 2) return
    const id = window.setInterval(() => step(1), speed.stepMs)
    return () => window.clearInterval(id)
  }, [playing, speed.stepMs, step, observations.length])

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void centerRef.current?.requestFullscreen?.()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || modal) return
      const key = e.key.toLowerCase()
      if (e.key === '?') return setModal('help')
      if (observations.length === 0) return
      if (e.key === ' ') {
        e.preventDefault()
        if (observations.length > 1) setPlaying((p) => !p)
      } else if (e.key === 'ArrowRight') step(1)
      else if (e.key === 'ArrowLeft') step(-1)
      else if (key === 'o') setMode('original')
      else if (key === 's' && observations.length > 1) setMode('swipe')
      else if (key === 'g') setShowGrid((v) => !v)
      else if (key === 'k') setShowKnown((v) => !v)
      else if (key === 'f') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, observations.length, modal, toggleFullscreen])

  const epochUrl = useCallback(
    (i: number) => {
      if (!images?.epochs?.length) return null
      const obs = observations[i]
      const ep = obs ? images.epochs.find((e) => e.observationId === obs.id) : images.epochs[i]
      if (diffMode) {
        return ep?.residualUrl ?? images.differences?.[i]?.url ?? ep?.url ?? null
      }
      return ep?.url ?? null
    },
    [images, observations, diffMode],
  )

  const canSwipe = observations.length > 1
  const swipeOn = mode === 'swipe' && canSwipe

  const view = useMemo(() => {
    if (!images || observations.length === 0) return null
    const epochLabel = (i: number) => t('badge.epochN', { n: i + 1 })
    if (swipeOn) {
      const ref = referenceIndex === activeIndex ? (activeIndex === 0 ? Math.min(1, observations.length - 1) : 0) : referenceIndex
      return {
        url: epochUrl(activeIndex),
        compareUrl: epochUrl(ref),
        compareLabels: [`A · ${epochLabel(ref)}`, `B · ${epochLabel(activeIndex)}`] as [string, string],
        colorApplicable: true,
        displayedIndex: activeIndex,
        badge: t('badge.swipe', { ref: ref + 1, n: activeIndex + 1 }),
      }
    }
    return {
      url: epochUrl(activeIndex),
      colorApplicable: true,
      displayedIndex: activeIndex,
      badge: t('badge.original', { n: activeIndex + 1 }),
    }
  }, [images, observations, swipeOn, activeIndex, referenceIndex, epochUrl, t])

  const baseUrl = useProcessedImage(view?.url ?? null, imageSettings, view?.colorApplicable ?? false)
  const compareUrl = useProcessedImage(view?.compareUrl ?? null, imageSettings, true)
  const imageFilter = view && !view.colorApplicable && !isDefaultSettings(imageSettings) ? cssFilterFor(imageSettings) : undefined

  const displayed = view ? observations[view.displayedIndex] : null
  const selectedCandidate = candidates.find((c) => c.id === selectedCandidateId) ?? null
  const busy = ['submitting', 'pending', 'processing', 'loading-results'].includes(phase)

  const knownMatches = useMemo(() => {
    const map = new Map<string, KnownObject>()
    const tol = 2.5 * ((images?.width ?? 64) / 64)
    for (const c of candidates) {
      const hit = knownObjects.find((k) => matchTrack(c.detections, k.positions, tol))
      if (hit) map.set(c.id, hit)
    }
    return map
  }, [candidates, knownObjects, images])

  const pmShift = useMemo(() => {
    if ((pmra === 0 && pmdec === 0) || !observations.length || !images) return undefined
    const firstMjd = (observations[0]?.metadata?.mjd as number) || 0
    const currentMjd = (observations[activeIndex]?.metadata?.mjd as number) || firstMjd
    const dtYears = firstMjd > 0 && currentMjd > 0 ? (currentMjd - firstMjd) / 365.25 : 0
    const ps = images.pixelScaleArcsec || 6.2
    return {
      x: (pmra * 1e-3 * dtYears) / ps,
      y: (pmdec * 1e-3 * dtYears) / ps,
    }
  }, [pmra, pmdec, observations, activeIndex, images])

  useEffect(() => {
    if (!lastQuery || candidates.length === 0) return
    let active = true

    const mjd = (observations[0]?.metadata?.mjd as number) || 60000.0
    Promise.all([
      fetchGaiaHighPMStars(lastQuery.ra, lastQuery.dec, 150),
      fetchKnownAsteroidsSkyBoT(lastQuery.ra, lastQuery.dec, mjd, 200),
      fetchNEOSSatObservations(lastQuery.ra, lastQuery.dec, 300),
    ])
      .then(([gaiaList, skybotList, neossatList]) => {
        if (!active) return
        const map = new Map<string, KnownCatalogObject>()

        for (const cand of candidates) {
          const hitSkybot = skybotList.find((ast) => {
            const dRa = (cand.ra - ast.ra) * Math.cos((cand.dec * Math.PI) / 180)
            const dDec = cand.dec - ast.dec
            return Math.hypot(dRa, dDec) * 3600 < 4.0
          })
          if (hitSkybot) {
            map.set(cand.id, hitSkybot)
            continue
          }

          const hitGaia = gaiaList.find((g) => {
            const dRa = (cand.ra - g.ra) * Math.cos((cand.dec * Math.PI) / 180)
            const dDec = cand.dec - g.dec
            return Math.hypot(dRa, dDec) * 3600 < 3.0
          })
          if (hitGaia) {
            map.set(cand.id, hitGaia)
            continue
          }

          const hitNeossat = neossatList.find((neo) => {
            const dRa = (cand.ra - neo.ra) * Math.cos((cand.dec * Math.PI) / 180)
            const dDec = cand.dec - neo.dec
            return Math.hypot(dRa, dDec) * 3600 < 8.0
          })
          if (hitNeossat) {
            map.set(cand.id, hitNeossat)
          }
        }
        setLiveMatches(map)
      })
      .catch(() => {})

    return () => {
      active = false
    }
  }, [lastQuery?.ra, lastQuery?.dec, candidates, observations])

  async function copyLink() {
    await navigator.clipboard?.writeText(window.location.href).catch(() => undefined)
    showToast(t('toolbar.linkCopied'))
  }

  async function onExportGif() {
    if (!images || !lastQuery) return
    setExporting(true)
    try {
      const label = (i: number) => `${t('badge.epochN', { n: i + 1 })} · ${formatTimestamp(observations[i].timestamp).slice(0, 10)}`
      const processed = async (url: string) => (isDefaultSettings(imageSettings) ? url : processImage(url, imageSettings))
      const frames: GifFrame[] = await Promise.all(
        observations.map(async (_, i) => ({ url: await processed(epochUrl(i)!), label: label(i) })),
      )
      await exportGif(frames, 900, `spherex_${lastQuery.ra}_${lastQuery.dec}.gif`, t('app.title'))
      showToast(t('toolbar.gifReady'))
    } catch {
      showToast(t('toolbar.gifError'))
    } finally {
      setExporting(false)
    }
  }

  function closeIntro() {
    try {
      localStorage.setItem(INTRO_KEY, '1')
    } catch {
      // localStorage no disponible
    }
    setModal(null)
  }

  function startExploringDemo() {
    closeIntro()
    setExternalQuery({ ...DEMO_QUERY })
    runSearch(DEMO_QUERY)
  }

  if (!entered) {
    return (
      <HomePage
        onEnter={() => {
          try {
            sessionStorage.setItem(ENTERED_KEY, '1')
          } catch {
            // ignore
          }
          setEntered(true)
        }}
      />
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <button
          type="button"
          className="brand brand-btn"
          onClick={() => {
            try {
              sessionStorage.removeItem(ENTERED_KEY)
            } catch {
              // ignore
            }
            setEntered(false)
          }}
          title={t('home.backHome')}
        >
          <img className="logo-img" src="/team-logo.jpg" alt="" width={36} height={36} />
          <div>
            <h1>{t('app.title')}</h1>
            <p className="muted small">{t('app.subtitle')}</p>
          </div>
        </button>
        <div className="topbar-right">
          {analysis.info && (
            <span className={`pill status-pill phase-${phase}`}>
              {analysis.info.id} · {t(`phase.${phase}`)}
            </span>
          )}
          <nav className="topnav">
            <button className="nav-btn" onClick={() => setModal('intro')} title={t('nav.intro')}>
              ✦ <span>{t('nav.intro')}</span>
            </button>
            <button className="nav-btn" onClick={() => setModal('guide')} title={t('nav.guide')}>
              🧭 <span>{t('nav.guide')}</span>
            </button>
            <button className="nav-btn" onClick={() => setModal('help')} title={t('nav.help')}>
              ⌨
            </button>
            <button className="nav-btn" onClick={() => setModal('about')} title={t('nav.about')}>
              ⓘ
            </button>
          </nav>
          <LanguageSelector />
        </div>
      </header>

      <aside className="sidebar left">
        <SearchPanel busy={busy} onSubmit={runSearch} externalQuery={externalQuery} />
      </aside>

      <main className="center" ref={centerRef}>
        <div className="toolbar">
          <div className="segmented">
            {VIEW_MODES.map((m) => (
              <button
                key={m}
                className={mode === m ? 'active' : ''}
                onClick={() => setMode(m)}
                disabled={!view || (m === 'swipe' && !canSwipe)}
                title={m === 'swipe' && !canSwipe ? t('toolbar.swipeNeedsEpochs') : undefined}
              >
                <span className="mode-icon">{MODE_ICON[m]}</span> {t(`modes.${m}`)}
              </button>
            ))}
          </div>
          <div className="toggles">
            <label>
              <input type="checkbox" checked={showOverlays} onChange={(e) => setShowOverlays(e.target.checked)} />
              {t('toolbar.candidates')}
            </label>
            <label>
              <input type="checkbox" checked={showTrajectories} onChange={(e) => setShowTrajectories(e.target.checked)} disabled={!showOverlays} />
              {t('toolbar.trajectories')}
            </label>
            <label>
              <input type="checkbox" checked={showKnown} onChange={(e) => setShowKnown(e.target.checked)} />
              {t('toolbar.known')}
            </label>
            <label>
              <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} />
              {t('toolbar.grid')}
            </label>
            <label style={{ fontWeight: 'bold', color: diffMode ? '#38bdf8' : 'inherit' }} title="Resta de mediana temporal (WiseView): elimina estrellas fijas y luz zodiacal">
              <input
                type="checkbox"
                checked={diffMode}
                onChange={(e) => {
                  const val = e.target.checked
                  setDiffMode(val)
                  setWiseState({ diff: val })
                }}
              />
              ✨ Diff (Sin Estrellas)
            </label>
            <div className="track-stack-inputs" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#94a3b8' }}>
              <span>Track & Stack:</span>
              <input
                type="number"
                placeholder="PM RA"
                value={pmra || ''}
                onChange={(e) => {
                  const val = parseFloat(e.target.value) || 0
                  setPmra(val)
                  setWiseState({ pmra: val })
                }}
                style={{ width: '56px', background: '#0b1021', border: '1px solid #334155', color: '#f8fafc', borderRadius: '4px', padding: '1px 4px', fontSize: '11px' }}
                title="Movimiento Propio en RA (mas/año)"
              />
              <input
                type="number"
                placeholder="PM Dec"
                value={pmdec || ''}
                onChange={(e) => {
                  const val = parseFloat(e.target.value) || 0
                  setPmdec(val)
                  setWiseState({ pmdec: val })
                }}
                style={{ width: '56px', background: '#0b1021', border: '1px solid #334155', color: '#f8fafc', borderRadius: '4px', padding: '1px 4px', fontSize: '11px' }}
                title="Movimiento Propio en Dec (mas/año)"
              />
            </div>
          </div>
          <div className="toggles feature-toggles" title={t('toolbar.layersHint')}>
            <span className="toggles-label">{t('toolbar.layers')}</span>
            {SPECTRAL_FEATURES.map((f) => {
              const on = activeFeatures.includes(f.id)
              const available = images?.featureLayers?.some((l) => l.id === f.id)
              return (
                <label key={f.id} className={`feature-toggle feature-${f.id} ${!available ? 'unavailable' : ''}`}>
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={!available}
                    onChange={(e) => {
                      const on = e.target.checked
                      setActiveFeatures((cur) => (on ? [...cur, f.id] : cur.filter((id) => id !== f.id)))
                      if (on) showToast(t(`search.features.${f.id}On`))
                    }}
                  />
                  {t(`search.features.${f.id}`)}
                </label>
              )
            })}
          </div>
          <div className="tools">
            <ImageControls settings={imageSettings} onChange={setImageSettings} colorApplicable={view?.colorApplicable ?? true} />
            <button className="tool-btn" onClick={copyLink} disabled={!lastQuery} title={t('toolbar.copyLink')}>
              🔗
            </button>
            <button className="tool-btn" onClick={onExportGif} disabled={!view || exporting} title={t('toolbar.exportGif')}>
              {exporting ? '…' : 'GIF'}
            </button>
            <button className="tool-btn" onClick={toggleFullscreen} title={t('toolbar.fullscreen')}>
              ⛶
            </button>
          </div>
        </div>

        <SkyViewer
          imageUrl={baseUrl}
          compareUrl={swipeOn ? compareUrl : null}
          compareLabels={view?.compareLabels}
          imageFilter={imageFilter}
          width={Math.max(1, images?.width ?? 64)}
          height={Math.max(1, images?.height ?? 64)}
          pixelScaleArcsec={images?.pixelScaleArcsec ?? 6.2}
          region={analysis.info?.region ?? null}
          candidates={candidates}
          knownObjects={knownObjects}
          activeObservationId={displayed?.id ?? null}
          selectedCandidateId={selectedCandidateId}
          onSelectCandidate={setSelectedCandidateId}
          showOverlays={showOverlays}
          showTrajectories={showTrajectories}
          showKnown={showKnown}
          showGrid={showGrid}
          featureLayers={images?.featureLayers}
          activeFeatureIds={activeFeatures}
          crossfade={mode === 'original'}
          pmShift={pmShift}
          badge={view?.badge}
          placeholder={
            <StatusView
              phase={phase}
              progress={analysis.info?.progress}
              message={analysis.info?.message}
              error={analysis.error}
              onRetry={lastQuery ? () => runSearch(lastQuery) : undefined}
            />
          }
        />

        {displayed && (
          <div className="obs-info">
            <div>
              <span className="label">{t('obsInfo.date')}</span>
              {formatTimestamp(displayed.timestamp)}
            </div>
            <div>
              <span className="label">{t('obsInfo.detector')}</span>
              {displayed.detector}
            </div>
            <div>
              <span className="label">{t('obsInfo.channel')}</span>
              {Array.isArray(displayed.metadata?.bands)
                ? t('obsInfo.bandsCount', { n: (displayed.metadata.bands as number[]).length })
                : typeof displayed.metadata?.group === 'number'
                  ? displayed.metadata.group
                  : (lastQuery?.group ?? '—')}
            </div>
            <div>
              <span className="label">{t('obsInfo.wavelength')}</span>
              {displayed.wavelength?.toFixed(4) ?? '—'}
              {displayed.bandwidth ? ` ± ${(displayed.bandwidth / 2).toFixed(4)}` : ''} {displayed.spectral_unit}
            </div>
            <div>
              <span className="label">{t('obsInfo.invalidPixels')}</span>
              {displayed.n_invalid_pixels ?? '—'}
            </div>
            <div className="ellipsis" title={displayed.fits_source}>
              <span className="label">{t('obsInfo.id')}</span>
              {displayed.id}
            </div>
          </div>
        )}

        <div className="playback">
          <Filmstrip
            observations={observations}
            epochs={images?.epochs ?? []}
            activeIndex={activeIndex}
            referenceIndex={referenceIndex}
            onSelect={setActiveIndex}
          />
          <Timeline observations={observations} activeIndex={activeIndex} referenceIndex={referenceIndex} onSelect={setActiveIndex} />
          <div className="controls">
            <button className="btn" onClick={() => step(-1)} disabled={!view || observations.length < 2}>
              {t('playback.previous')}
            </button>
            <button
              className="btn primary"
              onClick={() => setPlaying((p) => !p)}
              disabled={!view || observations.length < 2}
            >
              {playing ? t('playback.pause') : t('playback.play')}
            </button>
            <button className="btn" onClick={() => step(1)} disabled={!view || observations.length < 2}>
              {t('playback.next')}
            </button>
            <div className="speed" title={t('playback.speed')}>
              {SPEEDS.map((s, i) => (
                <button
                  key={s.label}
                  type="button"
                  className={`chip ${speedLevel === i ? 'active' : ''}`}
                  onClick={() => setSpeedLevel(i)}
                  disabled={!view || observations.length < 2}
                >
                  {s.label}
                </button>
              ))}
            </div>
            {swipeOn && (
              <button
                className="btn ghost"
                onClick={() => setReferenceIndex(activeIndex)}
                disabled={!view}
                title={t('playback.setReferenceHint')}
              >
                {t('playback.setReference')}
              </button>
            )}
          </div>
        </div>
      </main>

      <aside className="sidebar right">
        <CandidateList
          candidates={candidates}
          selectedId={selectedCandidateId}
          onSelect={setSelectedCandidateId}
          knownMatches={knownMatches}
          liveCatalogMatches={liveMatches}
        />
        <CandidateDetails
          candidate={selectedCandidate}
          knownMatch={selectedCandidate ? knownMatches.get(selectedCandidate.id) ?? null : null}
          liveCatalogMatch={selectedCandidate ? liveMatches.get(selectedCandidate.id) ?? null : null}
        />
      </aside>

      {toast && <div className="toast">{toast}</div>}

      {modal === 'intro' && (
        <IntroModal
          onClose={closeIntro}
          onStartExploring={startExploringDemo}
          onOpenGuide={() => {
            closeIntro()
            setModal('guide')
          }}
        />
      )}
      {modal === 'guide' && <FieldGuideModal onClose={() => setModal(null)} />}
      {modal === 'help' && <HelpModal onClose={() => setModal(null)} />}
      {modal === 'about' && <AboutModal onClose={() => setModal(null)} />}
    </div>
  )
}
