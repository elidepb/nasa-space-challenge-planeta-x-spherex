import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { useI18n } from '../i18n/I18nProvider'
import type { HunterMark } from '../lib/hunter'
import { formatDecDms, formatRaHms, pixelToSky } from '../lib/sky'
import type { Candidate, FeatureLayerImage, KnownObject, RegionQuery } from '../types/contracts'

interface Props {
  imageUrl: string | null
  /** Imagen del lado izquierdo en modo deslizador. */
  compareUrl?: string | null
  compareLabels?: [string, string]
  imageFilter?: string
  width: number
  height: number
  pixelScaleArcsec: number
  region: RegionQuery | null
  candidates: Candidate[]
  knownObjects: KnownObject[]
  activeObservationId: string | null
  selectedCandidateId: string | null
  onSelectCandidate: (id: string) => void
  showOverlays: boolean
  showTrajectories: boolean
  showKnown: boolean
  showGrid: boolean
  /** Capas espectrales activas (polvo / gases / H). */
  featureLayers?: FeatureLayerImage[]
  activeFeatureIds?: string[]
  /** Crossfade al cambiar de época (desactivado en blink/swipe). */
  crossfade?: boolean
  hunterActive: boolean
  hunterMarks: HunterMark[]
  onHunterMark: (x: number, y: number) => void
  badge?: ReactNode
  placeholder?: ReactNode
}

const CROSSFADE_MS = 1000

interface View {
  k: number
  x: number
  y: number
}

const MIN_K = 1
const MAX_K = 16
const IDENTITY: View = { k: 1, x: 0, y: 0 }
const CLICK_TOLERANCE_PX = 4
const NICE_ARCSEC = [1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200]

export function SkyViewer(props: Props) {
  const { imageUrl, compareUrl, width, height, candidates, activeObservationId, selectedCandidateId } = props
  const { t } = useI18n()
  const stageRef = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<View>(IDENTITY)
  const [stageW, setStageW] = useState(600)
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null)
  const [pin, setPin] = useState<{ x: number; y: number } | null>(null)
  const [split, setSplit] = useState(0.5)
  const [copied, setCopied] = useState(false)
  const [shownUrl, setShownUrl] = useState<string | null>(imageUrl)
  const [outgoingUrl, setOutgoingUrl] = useState<string | null>(null)
  const [fadeActive, setFadeActive] = useState(false)
  const shownRef = useRef<string | null>(imageUrl)
  const drag = useRef<{ px: number; py: number; vx: number; vy: number; moved: boolean } | null>(null)
  const splitDrag = useRef(false)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<{ dist: number; mx: number; my: number } | null>(null)
  const reduceMotion = useRef(
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  )

  const hasImage = imageUrl !== null

  useEffect(() => {
    if (!imageUrl) {
      shownRef.current = null
      setShownUrl(null)
      setOutgoingUrl(null)
      setFadeActive(false)
      return
    }
    if (imageUrl === shownRef.current) return
    const previous = shownRef.current
    const canFade = Boolean(props.crossfade && !compareUrl && !reduceMotion.current && previous)
    shownRef.current = imageUrl
    if (!canFade) {
      setShownUrl(imageUrl)
      setOutgoingUrl(null)
      setFadeActive(false)
      return
    }
    setOutgoingUrl(previous)
    setShownUrl(imageUrl)
    setFadeActive(false)
    // Dos frames: montar en opacity 0 y luego activar la transición.
    let raf2 = 0
    const raf1 = window.requestAnimationFrame(() => {
      raf2 = window.requestAnimationFrame(() => setFadeActive(true))
    })
    const done = window.setTimeout(() => {
      setOutgoingUrl(null)
      setFadeActive(false)
    }, CROSSFADE_MS)
    return () => {
      window.cancelAnimationFrame(raf1)
      window.cancelAnimationFrame(raf2)
      window.clearTimeout(done)
    }
  }, [imageUrl, compareUrl, props.crossfade])

  useEffect(() => {
    const el = stageRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      setView((v) => zoomAt(v, e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.2 : 1 / 1.2, rect.width, rect.height))
    }
    const ro = new ResizeObserver(([entry]) => setStageW(entry.contentRect.width))
    el.addEventListener('wheel', onWheel, { passive: false })
    ro.observe(el)
    return () => {
      el.removeEventListener('wheel', onWheel)
      ro.disconnect()
    }
  }, [hasImage])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPin(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function zoomBy(factor: number) {
    const rect = stageRef.current?.getBoundingClientRect()
    if (!rect) return
    setView((v) => zoomAt(v, rect.width / 2, rect.height / 2, factor, rect.width, rect.height))
  }

  function toImage(clientX: number, clientY: number) {
    const rect = stageRef.current!.getBoundingClientRect()
    return {
      x: ((clientX - rect.left - view.x) / view.k / rect.width) * width,
      y: ((clientY - rect.top - view.y) / view.k / rect.height) * height,
    }
  }

  function pinchState() {
    const [a, b] = [...pointers.current.values()]
    return { dist: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 }
  }

  function onPointerDown(e: ReactPointerEvent) {
    if (e.button !== 0) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pointers.current.size === 2) {
      drag.current = null
      pinch.current = pinchState()
      return
    }
    if (pointers.current.size > 2) return
    drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y, moved: false }
  }

  function onPointerMove(e: ReactPointerEvent) {
    const rect = stageRef.current!.getBoundingClientRect()
    if (pointers.current.has(e.pointerId)) pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pinch.current && pointers.current.size >= 2) {
      const prev = pinch.current
      const next = pinchState()
      pinch.current = next
      setView((v) => {
        const z = zoomAt(v, next.mx - rect.left, next.my - rect.top, next.dist / Math.max(prev.dist, 1), rect.width, rect.height)
        return clampView({ ...z, x: z.x + next.mx - prev.mx, y: z.y + next.my - prev.my }, rect.width, rect.height)
      })
      return
    }
    if (splitDrag.current) {
      setSplit(Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)))
      return
    }
    const d = drag.current
    if (d) {
      if (Math.hypot(e.clientX - d.px, e.clientY - d.py) > CLICK_TOLERANCE_PX) d.moved = true
      if (d.moved) {
        setView((v) => clampView({ ...v, x: d.vx + e.clientX - d.px, y: d.vy + e.clientY - d.py }, rect.width, rect.height))
      }
    }
    const p = toImage(e.clientX, e.clientY)
    setHover(p.x >= 0 && p.y >= 0 && p.x < width && p.y < height ? p : null)
  }

  function onPointerCancel(e: ReactPointerEvent) {
    pointers.current.delete(e.pointerId)
    if (pointers.current.size < 2) pinch.current = null
    drag.current = null
    splitDrag.current = false
  }

  function onPointerUp(e: ReactPointerEvent) {
    pointers.current.delete(e.pointerId)
    if (pinch.current || pointers.current.size > 0) {
      if (pointers.current.size < 2) pinch.current = null
      drag.current = null
      return
    }
    splitDrag.current = false
    const d = drag.current
    drag.current = null
    if (!d || d.moved) return
    const p = toImage(e.clientX, e.clientY)
    if (p.x < 0 || p.y < 0 || p.x >= width || p.y >= height) return
    // Centro del píxel = coordenada entera, igual que las detecciones del backend.
    const ix = p.x - 0.5
    const iy = p.y - 0.5
    if (props.hunterActive) props.onHunterMark(ix, iy)
    else setPin({ x: ix, y: iy })
  }

  const toSky = (x: number, y: number) =>
    props.region ? pixelToSky(props.region, props.pixelScaleArcsec, width, height, x, y) : null
  const hoverSky = hover ? toSky(hover.x - 0.5, hover.y - 0.5) : null
  const pinSky = pin ? toSky(pin.x, pin.y) : null

  const u = width / 64
  const markerR = (2.6 * u) / Math.sqrt(view.k)
  const fontSize = (2.6 * u) / view.k
  const pxPerArcsec = (stageW * view.k) / (width * props.pixelScaleArcsec)
  const scaleArcsec = NICE_ARCSEC.filter((s) => s * pxPerArcsec <= 120).pop() ?? NICE_ARCSEC[0]
  const gridArcsec = NICE_ARCSEC.find((s) => s * pxPerArcsec >= 90) ?? NICE_ARCSEC[NICE_ARCSEC.length - 1]
  const splitContent = ((split * stageW - view.x) / view.k / stageW) * 100

  async function copyPin() {
    if (!pinSky) return
    await navigator.clipboard?.writeText(`${pinSky.ra.toFixed(6)} ${pinSky.dec.toFixed(6)}`).catch(() => undefined)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  if (!imageUrl) {
    return (
      <div className="viewer">
        <div className="viewer-stage empty">{props.placeholder}</div>
      </div>
    )
  }

  return (
    <div className="viewer">
      <div
        ref={stageRef}
        className={`viewer-stage ${drag.current?.moved ? 'dragging' : ''} ${props.hunterActive ? 'hunting' : ''}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        onPointerLeave={() => setHover(null)}
        onDoubleClick={() => setView(IDENTITY)}
      >
        <div className="viewer-content" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})` }}>
          {shownUrl && (
            <img
              src={shownUrl}
              alt={t('viewer.alt')}
              draggable={false}
              className={`viewer-image crossfade-in ${outgoingUrl ? (fadeActive ? 'is-visible' : 'is-hidden') : 'is-visible'}`}
              style={{ filter: props.imageFilter }}
            />
          )}
          {outgoingUrl && (
            <img
              src={outgoingUrl}
              alt=""
              draggable={false}
              className={`viewer-image crossfade-out ${fadeActive ? 'is-fading' : ''}`}
              style={{ filter: props.imageFilter }}
            />
          )}
          {outgoingUrl && <div className={`viewer-fade-veil ${fadeActive ? 'is-active' : ''}`} aria-hidden />}
          {compareUrl && (
            <img
              src={compareUrl}
              alt=""
              draggable={false}
              className="viewer-image compare"
              style={{ filter: props.imageFilter, clipPath: `inset(0 ${Math.max(0, 100 - splitContent)}% 0 0)` }}
            />
          )}
          {(props.featureLayers ?? [])
            .filter((layer) => props.activeFeatureIds?.includes(layer.id))
            .map((layer) => (
              <img
                key={layer.id}
                src={layer.url}
                alt=""
                draggable={false}
                className={`viewer-image feature-layer feature-${layer.id}`}
              />
            ))}
          <svg className="viewer-overlay" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            {props.showGrid && props.region && (
              <Grid
                region={props.region}
                width={width}
                height={height}
                pixelScaleArcsec={props.pixelScaleArcsec}
                spacingArcsec={gridArcsec}
                fontSize={fontSize * 0.8}
              />
            )}

            {props.showKnown &&
              props.knownObjects.map((obj) => {
                const current = obj.positions.find((p) => p.observationId === activeObservationId)
                const anchor = current ?? obj.positions[0]
                if (!anchor) return null
                const r = markerR * 1.15
                return (
                  <g key={obj.name} className="known">
                    {obj.positions.length > 1 && (
                      <polyline className="known-track" points={obj.positions.map((p) => `${p.x + 0.5},${p.y + 0.5}`).join(' ')} />
                    )}
                    <rect
                      className={`known-marker ${current ? '' : 'absent'}`}
                      x={anchor.x + 0.5 - r}
                      y={anchor.y + 0.5 - r}
                      width={r * 2}
                      height={r * 2}
                      transform={`rotate(45 ${anchor.x + 0.5} ${anchor.y + 0.5})`}
                    />
                    <text x={anchor.x + 0.5 + r * 1.3} y={anchor.y + 0.5 + r * 1.6} fontSize={fontSize * 0.9} className="known-label">
                      {obj.name}
                    </text>
                  </g>
                )
              })}

            {props.showOverlays &&
              candidates.map((c) => {
                const selected = c.id === selectedCandidateId
                const current = c.detections.find((d) => d.observationId === activeObservationId)
                const anchor = current ?? c.detections[0]
                return (
                  <g
                    key={c.id}
                    className={`cand cand-${c.status} ${selected ? 'selected' : ''}`}
                    onPointerDown={(e) => !props.hunterActive && e.stopPropagation()}
                    onPointerUp={(e) => !props.hunterActive && e.stopPropagation()}
                    onClick={() => !props.hunterActive && props.onSelectCandidate(c.id)}
                  >
                    {props.showTrajectories && c.detections.length > 1 && (
                      <>
                        <polyline className="cand-track" points={c.detections.map((d) => `${d.x + 0.5},${d.y + 0.5}`).join(' ')} />
                        {c.detections.map((d) => (
                          <circle key={d.observationId} className="cand-step" cx={d.x + 0.5} cy={d.y + 0.5} r={markerR * 0.28} />
                        ))}
                      </>
                    )}
                    <circle className={`cand-marker ${current ? '' : 'absent'}`} cx={anchor.x + 0.5} cy={anchor.y + 0.5} r={markerR} />
                    <text x={anchor.x + 0.5 + markerR * 1.2} y={anchor.y + 0.5 - markerR * 1.1} fontSize={fontSize} className="cand-label">
                      {c.id}
                    </text>
                  </g>
                )
              })}

            {props.hunterActive && props.hunterMarks.length > 0 && (
              <g className="hunter">
                {props.hunterMarks.length > 1 && (
                  <polyline className="hunter-track" points={props.hunterMarks.map((m) => `${m.x + 0.5},${m.y + 0.5}`).join(' ')} />
                )}
                {props.hunterMarks.map((m, i) => {
                  const current = m.observationId === activeObservationId
                  const r = markerR * (current ? 1 : 0.6)
                  const cx = m.x + 0.5
                  const cy = m.y + 0.5
                  return (
                    <g key={m.observationId} className={`hunter-mark ${current ? 'current' : ''}`}>
                      <line x1={cx - r * 1.6} y1={cy} x2={cx - r * 0.5} y2={cy} />
                      <line x1={cx + r * 0.5} y1={cy} x2={cx + r * 1.6} y2={cy} />
                      <line x1={cx} y1={cy - r * 1.6} x2={cx} y2={cy - r * 0.5} />
                      <line x1={cx} y1={cy + r * 0.5} x2={cx} y2={cy + r * 1.6} />
                      <text x={cx + r * 1.2} y={cy + r * 2.4} fontSize={fontSize * 0.8} className="hunter-label">
                        {i + 1}
                      </text>
                    </g>
                  )
                })}
              </g>
            )}

            {pin && (
              <g className="pin">
                <circle cx={pin.x + 0.5} cy={pin.y + 0.5} r={markerR * 0.9} />
                <line x1={pin.x + 0.5} y1={pin.y + 0.5 - markerR * 2} x2={pin.x + 0.5} y2={pin.y + 0.5 + markerR * 2} />
                <line x1={pin.x + 0.5 - markerR * 2} y1={pin.y + 0.5} x2={pin.x + 0.5 + markerR * 2} y2={pin.y + 0.5} />
              </g>
            )}
          </svg>
        </div>

        {compareUrl && (
          <>
            <div
              className="split-handle"
              style={{ left: `${split * 100}%` }}
              onPointerDown={(e) => {
                e.stopPropagation()
                ;(e.currentTarget.parentElement as HTMLElement).setPointerCapture(e.pointerId)
                splitDrag.current = true
              }}
            >
              <span>⇔</span>
            </div>
            {props.compareLabels && (
              <>
                <span className="split-label left">{props.compareLabels[0]}</span>
                <span className="split-label right">{props.compareLabels[1]}</span>
              </>
            )}
          </>
        )}

        {props.badge && <div className="viewer-badge">{props.badge}</div>}

        <div className="viewer-zoom" onPointerDown={(e) => e.stopPropagation()} onPointerUp={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
          <button className="icon-btn" onClick={() => zoomBy(1.5)} title={t('viewer.zoomIn')}>
            +
          </button>
          <span className="zoom-level">{view.k.toFixed(1)}×</span>
          <button className="icon-btn" onClick={() => zoomBy(1 / 1.5)} title={t('viewer.zoomOut')}>
            −
          </button>
          <button className="icon-btn" onClick={() => setView(IDENTITY)} title={t('viewer.reset')}>
            ⟲
          </button>
        </div>

        <div className="viewer-hud">
          <svg className="compass" viewBox="0 0 44 44" aria-label={t('viewer.compass')}>
            <line x1="30" y1="30" x2="30" y2="8" />
            <line x1="30" y1="30" x2="8" y2="30" />
            <polygon points="30,4 27,10 33,10" />
            <polygon points="4,30 10,27 10,33" />
            <text x="30" y="4" dy="-0.2em" textAnchor="middle">
              N
            </text>
            <text x="2" y="24" textAnchor="start">
              E
            </text>
          </svg>
          <div className="scale-bar">
            <div className="scale-line" style={{ width: `${scaleArcsec * pxPerArcsec}px` }} />
            <span>{formatArcsec(scaleArcsec)}</span>
          </div>
        </div>

        {pin && pinSky && (
          <div className="pin-card" onPointerDown={(e) => e.stopPropagation()} onPointerUp={(e) => e.stopPropagation()}>
            <div>
              <span className="label">{t('viewer.pinned')}</span>
              <span className="mono">RA {formatRaHms(pinSky.ra)}</span>
              <span className="mono">Dec {formatDecDms(pinSky.dec)}</span>
              <span className="mono muted">
                {pinSky.ra.toFixed(5)}°, {pinSky.dec.toFixed(5)}°
              </span>
            </div>
            <div className="pin-actions">
              <button className="chip" onClick={copyPin}>
                {copied ? t('viewer.copied') : t('viewer.copy')}
              </button>
              <button className="icon-btn" onClick={() => setPin(null)} title={t('viewer.unpin')}>
                ×
              </button>
            </div>
          </div>
        )}

        <div className="viewer-readout">
          {hover && hoverSky ? (
            <>
              <span>
                px {Math.floor(hover.x)}, {Math.floor(hover.y)}
              </span>
              <span>RA {formatRaHms(hoverSky.ra)}</span>
              <span>Dec {formatDecDms(hoverSky.dec)}</span>
            </>
          ) : (
            <span className="muted">{props.hunterActive ? t('hunter.viewerHint') : t('viewer.help')}</span>
          )}
        </div>
      </div>
    </div>
  )
}

function Grid(props: {
  region: RegionQuery
  width: number
  height: number
  pixelScaleArcsec: number
  spacingArcsec: number
  fontSize: number
}) {
  const { region, width, height, pixelScaleArcsec: ps, spacingArcsec } = props
  const cy = (height - 1) / 2
  const cx = (width - 1) / 2
  const cosd = Math.cos((region.dec * Math.PI) / 180)
  const decStep = spacingArcsec / 3600
  const raStep = decStep / cosd
  const decTop = region.dec + ((cy + 0.5) * ps) / 3600
  const decBottom = region.dec - ((height - cy) * ps) / 3600
  const raLeft = region.ra + ((cx + 0.5) * ps) / 3600 / cosd
  const raRight = region.ra - ((width - cx) * ps) / 3600 / cosd

  const decLines: { y: number; dec: number }[] = []
  for (let d = Math.ceil(decBottom / decStep) * decStep; d <= decTop; d += decStep) {
    decLines.push({ y: cy - ((d - region.dec) * 3600) / ps + 0.5, dec: d })
  }
  const raLines: { x: number; ra: number }[] = []
  for (let r = Math.ceil(raRight / raStep) * raStep; r <= raLeft; r += raStep) {
    raLines.push({ x: cx - ((r - region.ra) * 3600 * cosd) / ps + 0.5, ra: r })
  }

  return (
    <g className="grid">
      {decLines.map((l) => (
        <g key={`d${l.dec}`}>
          <line x1={0} x2={width} y1={l.y} y2={l.y} />
          <text x={0.6} y={l.y - 0.4} fontSize={props.fontSize}>
            {formatDecDms(l.dec).replace(/\.\d″$/, '″')}
          </text>
        </g>
      ))}
      {raLines.map((l) => (
        <g key={`r${l.ra}`}>
          <line y1={0} y2={height} x1={l.x} x2={l.x} />
          <text x={l.x + 0.4} y={height - 0.8} fontSize={props.fontSize}>
            {formatRaHms(((l.ra % 360) + 360) % 360).replace(/\.\d\ds$/, 's')}
          </text>
        </g>
      ))}
    </g>
  )
}

function formatArcsec(v: number) {
  if (v >= 3600) return `${v / 3600}°`
  if (v >= 60) return `${v / 60}′`
  return `${v}″`
}

function zoomAt(v: View, mx: number, my: number, factor: number, w: number, h: number): View {
  const k = Math.min(MAX_K, Math.max(MIN_K, v.k * factor))
  const r = k / v.k
  return clampView({ k, x: mx - (mx - v.x) * r, y: my - (my - v.y) * r }, w, h)
}

function clampView(v: View, w: number, h: number): View {
  const minX = w - w * v.k
  const minY = h - h * v.k
  return { k: v.k, x: Math.min(0, Math.max(minX, v.x)), y: Math.min(0, Math.max(minY, v.y)) }
}
