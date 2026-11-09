import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_MODE } from './api'
import { CandidateDetails, CandidateList } from './components/CandidatePanel'
import { Filmstrip } from './components/Filmstrip'
import { HunterPanel } from './components/HunterPanel'
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
import { matchTrack, type HunterMark } from './lib/hunter'
import {
  cssFilterFor,
  DEFAULT_IMAGE_SETTINGS,
  isDefaultSettings,
  processImage,
  type ImageSettings,
} from './lib/imageProcessing'
import { formatTimestamp } from './lib/sky'
import { SPECTRAL_FEATURES, type SpectralFeatureId } from './lib/spectral'
import { readUrlState, VIEW_MODES, writeUrlState, type UrlState, type ViewMode } from './lib/urlState'
import type { KnownObject, RegionQuery } from './types/contracts'

const SPEEDS = [
  { label: '0.5×', stepMs: 2200, blinkMs: 1000 },
  { label: '1×', stepMs: 1400, blinkMs: 500 },
  { label: '2×', stepMs: 900, blinkMs: 250 },
]
const INTRO_KEY = 'spherex.introSeen'
const DEMO_QUERY: RegionQuery = {
  ra: 210.80227,
  dec: 54.34895,
  size: 0.05,
  qr: 'qr2',
  bandpass: 'SPHEREx-D2',
  group: 7,
  bands: [24],
}

type ModalName = 'intro' | 'guide' | 'help' | 'about' | null

const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

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

  const [lastQuery, setLastQuery] = useState<RegionQuery | null>(null)
  const [externalQuery, setExternalQuery] = useState<RegionQuery | null>(initialUrl.query)
  const [activeIndex, setActiveIndex] = useState(0)
  const [referenceIndex, setReferenceIndex] = useState(0)
  const [mode, setMode] = useState<ViewMode>('original')
  const [playing, setPlaying] = useState(false)
  const [speedLevel, setSpeedLevel] = useState(prefersReducedMotion() ? 0 : 1)
  const [blinkOnRef, setBlinkOnRef] = useState(false)
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const [showOverlays, setShowOverlays] = useState(true)
  const [showTrajectories, setShowTrajectories] = useState(true)
  const [showKnown, setShowKnown] = useState(false)
  const [showGrid, setShowGrid] = useState(false)
  const [activeFeatures, setActiveFeatures] = useState<SpectralFeatureId[]>([])
  const [imageSettings, setImageSettings] = useState<ImageSettings>(DEFAULT_IMAGE_SETTINGS)
  const [hunterActive, setHunterActive] = useState(false)
  const [hunterMarks, setHunterMarks] = useState<HunterMark[]>([])
  const [autoAdvance, setAutoAdvance] = useState(true)
  const [modal, setModal] = useState<ModalName>(initialUrl.query || introAlreadySeen() ? null : 'intro')
  const [toast, setToast] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

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

  useEffect(() => {
    if (initialUrl.query) runSearch(initialUrl.query)
  }, [])

  // Nuevo resultado: restablecer vista (o aplicar la de una URL compartida).
  useEffect(() => {
    if (!result) return
    const n = observations.length
    const refId = images?.differences[0]?.referenceId
    setReferenceIndex(Math.max(0, refId ? observations.findIndex((o) => o.id === refId) : 0))
    setPlaying(false)
    setHunterMarks([])
    const pending = pendingView.current
    pendingView.current = null
    if (pending) {
      setMode(pending.mode ?? 'original')
      setActiveIndex(Math.min(n - 1, Math.max(0, pending.epoch ?? n - 1)))
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

  // Precarga de imágenes para que el blink no espere a la red.
  useEffect(() => {
    if (!images) return
    for (const url of [...images.epochs.map((e) => e.url), ...images.differences.map((d) => d.url)]) {
      new Image().src = url
    }
  }, [images])

  useEffect(() => {
    if (!images || isDefaultSettings(imageSettings)) return
    images.epochs.forEach((e) => void processImage(e.url, imageSettings).catch(() => undefined))
  }, [images, imageSettings])

  const differenceFor = useCallback(
    (index: number) => images?.differences.find((d) => d.observationId === observations[index]?.id) ?? null,
    [images, observations],
  )

  const step = useCallback(
    (delta: number) => {
      const n = observations.length
      if (n === 0) return
      setActiveIndex((i) => {
        let next = (i + delta + n) % n
        if (mode === 'difference') {
          for (let tries = 0; tries < n && !differenceFor(next); tries++) next = (next + delta + n) % n
        }
        return next
      })
    },
    [observations.length, mode, differenceFor],
  )

  const speed = SPEEDS[speedLevel]
  useEffect(() => {
    if (!playing) return
    const id =
      mode === 'blink'
        ? setInterval(() => setBlinkOnRef((b) => !b), speed.blinkMs)
        : setInterval(() => step(1), speed.stepMs)
    return () => clearInterval(id)
  }, [playing, mode, speed, step])

  useEffect(() => {
    if (mode !== 'blink') setBlinkOnRef(false)
  }, [mode])

  const toggleHunter = useCallback(() => {
    setHunterActive((on) => {
      if (!on) {
        setPlaying(false)
        setMode((m) => (m === 'blink' ? 'original' : m))
      }
      return !on
    })
  }, [])

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
      if (e.key === 'ArrowRight') step(1)
      else if (e.key === 'ArrowLeft') step(-1)
      else if (e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (key === 'o') setMode('original')
      else if (key === 'b') setMode('blink')
      else if (key === 'd') setMode('difference')
      else if (key === 's') setMode('swipe')
      else if (key === 'h') toggleHunter()
      else if (key === 'g') setShowGrid((v) => !v)
      else if (key === 'k') setShowKnown((v) => !v)
      else if (key === 'f') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, observations.length, modal, toggleHunter, toggleFullscreen])

  const epochUrl = useCallback(
    (i: number) => images?.epochs.find((e) => e.observationId === observations[i]?.id)?.url ?? null,
    [images, observations],
  )

  const view = useMemo(() => {
    if (!images || observations.length === 0) return null
    const epochLabel = (i: number) => t('badge.epochN', { n: i + 1 })
    if (mode === 'blink') {
      const i = blinkOnRef ? referenceIndex : activeIndex
      return {
        url: epochUrl(i),
        colorApplicable: true,
        displayedIndex: i,
        badge: t('badge.blink', { frame: blinkOnRef ? 'A' : 'B', n: i + 1 }) + (i === referenceIndex ? t('badge.blinkRef') : ''),
      }
    }
    if (mode === 'difference') {
      const diff = differenceFor(activeIndex)
      if (!diff) {
        return { url: epochUrl(activeIndex), colorApplicable: true, displayedIndex: activeIndex, badge: t('badge.referenceNoDiff') }
      }
      const refIdx = observations.findIndex((o) => o.id === diff.referenceId)
      return {
        url: diff.url,
        colorApplicable: false,
        displayedIndex: activeIndex,
        badge: t('badge.difference', { n: activeIndex + 1, ref: refIdx + 1 }),
      }
    }
    if (mode === 'swipe') {
      return {
        url: epochUrl(activeIndex),
        compareUrl: epochUrl(referenceIndex),
        compareLabels: [`A · ${epochLabel(referenceIndex)}`, `B · ${epochLabel(activeIndex)}`] as [string, string],
        colorApplicable: true,
        displayedIndex: activeIndex,
        badge: t('badge.swipe', { ref: referenceIndex + 1, n: activeIndex + 1 }),
      }
    }
    return { url: epochUrl(activeIndex), colorApplicable: true, displayedIndex: activeIndex, badge: t('badge.original', { n: activeIndex + 1 }) }
  }, [images, observations, mode, blinkOnRef, activeIndex, referenceIndex, differenceFor, epochUrl, t])

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

  const onHunterMark = useCallback(
    (x: number, y: number) => {
      if (!displayed) return
      const next = [...hunterMarks.filter((m) => m.observationId !== displayed.id), { observationId: displayed.id, x, y }]
      setHunterMarks(next)
      if (!autoAdvance) return
      const marked = new Set(next.map((m) => m.observationId))
      const n = observations.length
      for (let k = 1; k < n; k++) {
        const idx = (view!.displayedIndex + k) % n
        if (!marked.has(observations[idx].id)) {
          setActiveIndex(idx)
          return
        }
      }
    },
    [displayed, hunterMarks, autoAdvance, observations, view],
  )

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
      let frames: GifFrame[]
      if (mode === 'blink' || mode === 'swipe') {
        frames = await Promise.all(
          [referenceIndex, activeIndex].map(async (i) => ({ url: await processed(epochUrl(i)!), label: label(i) })),
        )
      } else if (mode === 'difference') {
        frames = images.differences.map((d) => {
          const i = observations.findIndex((o) => o.id === d.observationId)
          return { url: d.url, label: `${t('modes.difference')} · ${label(i)}` }
        })
      } else {
        frames = await Promise.all(observations.map(async (_, i) => ({ url: await processed(epochUrl(i)!), label: label(i) })))
      }
      const delay = mode === 'blink' || mode === 'swipe' ? speed.blinkMs : speed.stepMs
      await exportGif(frames, delay, `spherex_${lastQuery.ra}_${lastQuery.dec}_${mode}.gif`, t('app.title'))
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

  function startHuntingDemo() {
    closeIntro()
    setExternalQuery({ ...DEMO_QUERY })
    runSearch(DEMO_QUERY)
    setHunterActive(true)
    setMode('original')
  }

  const markedIds = useMemo(() => new Set(hunterMarks.map((m) => m.observationId)), [hunterMarks])
  const modeIcon: Record<ViewMode, string> = { original: '▣', blink: '◑', difference: '±', swipe: '⇔' }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◎</span>
          <div>
            <h1>{t('app.title')}</h1>
            <p className="muted small">{t('app.subtitle')}</p>
          </div>
        </div>
        <div className="topbar-right">
          {analysis.info && (
            <span className={`pill status-pill phase-${phase}`}>
              {analysis.info.id} · {t(`phase.${phase}`)}
            </span>
          )}
          <span className={`pill ${API_MODE === 'mock' ? 'pill-warn' : 'pill-ok'}`}>
            {API_MODE === 'mock' ? t('app.mockData') : t('app.apiConnected')}
          </span>
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
              <button key={m} className={mode === m ? 'active' : ''} onClick={() => setMode(m)} disabled={!view}>
                <span className="mode-icon">{modeIcon[m]}</span> {t(`modes.${m}`)}
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
            <button className={`tool-btn hunt ${hunterActive ? 'active' : ''}`} onClick={toggleHunter} disabled={!view} title={t('hunter.toggle')}>
              🎯 <span>{t('hunter.button')}</span>
            </button>
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
          compareUrl={mode === 'swipe' ? compareUrl : null}
          compareLabels={view?.compareLabels}
          imageFilter={imageFilter}
          width={images?.width ?? 64}
          height={images?.height ?? 64}
          pixelScaleArcsec={images?.pixelScaleArcsec ?? 6.2}
          region={analysis.info?.region ?? null}
          candidates={candidates}
          knownObjects={knownObjects}
          activeObservationId={displayed?.id ?? null}
          selectedCandidateId={selectedCandidateId}
          onSelectCandidate={setSelectedCandidateId}
          showOverlays={showOverlays && !hunterActive}
          showTrajectories={showTrajectories}
          showKnown={showKnown}
          showGrid={showGrid}
          featureLayers={images?.featureLayers}
          activeFeatureIds={activeFeatures}
          crossfade={mode === 'original' || mode === 'difference'}
          hunterActive={hunterActive}
          hunterMarks={hunterMarks}
          onHunterMark={onHunterMark}
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
            markedIds={markedIds}
            onSelect={setActiveIndex}
          />
          <Timeline observations={observations} activeIndex={activeIndex} referenceIndex={referenceIndex} onSelect={setActiveIndex} />
          <div className="controls">
            <button className="btn" onClick={() => step(-1)} disabled={!view}>
              {t('playback.previous')}
            </button>
            <button className="btn primary" onClick={() => setPlaying((p) => !p)} disabled={!view || hunterActive}>
              {playing ? t('playback.pause') : mode === 'blink' ? t('playback.blink') : t('playback.play')}
            </button>
            <button className="btn" onClick={() => step(1)} disabled={!view}>
              {t('playback.next')}
            </button>
            <div className="speed" title={t('playback.speed')}>
              {SPEEDS.map((s, i) => (
                <button key={s.label} className={`chip ${speedLevel === i ? 'active' : ''}`} onClick={() => setSpeedLevel(i)} disabled={!view}>
                  {s.label}
                </button>
              ))}
            </div>
            <button
              className="btn ghost"
              onClick={() => setReferenceIndex(activeIndex)}
              disabled={!view || mode === 'difference'}
              title={t('playback.setReferenceHint')}
            >
              {t('playback.setReference')}
            </button>
          </div>
        </div>
      </main>

      <aside className="sidebar right">
        <CandidateList
          candidates={candidates}
          selectedId={selectedCandidateId}
          onSelect={setSelectedCandidateId}
          knownMatches={knownMatches}
        />
        {hunterActive && images && analysis.info ? (
          <HunterPanel
            observations={observations}
            marks={hunterMarks}
            region={analysis.info.region}
            images={images}
            knownObjects={knownObjects}
            candidates={candidates}
            activeObservationId={displayed?.id ?? null}
            autoAdvance={autoAdvance}
            onAutoAdvance={setAutoAdvance}
            onRemoveMark={(id) => setHunterMarks((ms) => ms.filter((m) => m.observationId !== id))}
            onClear={() => setHunterMarks([])}
            onSelectObservation={setActiveIndex}
            onSelectCandidate={(id) => {
              setHunterActive(false)
              setSelectedCandidateId(id)
            }}
            onExit={() => setHunterActive(false)}
            onToast={showToast}
          />
        ) : (
          <CandidateDetails
            candidate={selectedCandidate}
            knownMatch={selectedCandidate ? knownMatches.get(selectedCandidate.id) ?? null : null}
          />
        )}
      </aside>

      {toast && <div className="toast">{toast}</div>}

      {modal === 'intro' && (
        <IntroModal
          onClose={closeIntro}
          onStartHunting={startHuntingDemo}
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
