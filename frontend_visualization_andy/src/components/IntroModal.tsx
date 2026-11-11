import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { Modal } from './Modal'

interface Props {
  onClose: () => void
  onStartExploring: () => void
  onOpenGuide: () => void
}

const STARS = Array.from({ length: 26 }, (_, i) => {
  const a = Math.sin(i * 12.9898) * 43758.5453
  const b = Math.sin(i * 78.233) * 12345.6789
  return { x: 8 + (a - Math.floor(a)) * 224, y: 8 + (b - Math.floor(b)) * 124, r: 0.8 + ((i * 7) % 5) * 0.35 }
})

function BlinkDemo() {
  return (
    <svg className="blink-demo" viewBox="0 0 240 140" role="img">
      <rect width="240" height="140" rx="8" className="plate" />
      {STARS.map((s, i) => (
        <circle key={i} cx={s.x} cy={s.y} r={s.r} className="star" />
      ))}
      <circle cx="122" cy="62" r="2" className="mover frame-a" />
      <circle cx="134" cy="66" r="2" className="mover frame-b" />
      <circle cx="128" cy="64" r="11" className="mover-ring" />
    </svg>
  )
}

function SpectrumBar() {
  const { t } = useI18n()
  return (
    <div className="spectrum">
      <div className="spectrum-bar" />
      <div className="spectrum-labels small muted">
        <span>0.75 μm</span>
        <span>{t('intro.spectrumLabel')}</span>
        <span>5 μm</span>
      </div>
    </div>
  )
}

export function IntroModal({ onClose, onStartExploring, onOpenGuide }: Props) {
  const { t } = useI18n()
  const [step, setStep] = useState(0)

  const slides = [
    {
      kicker: '1930',
      title: t('intro.historyTitle'),
      body: (
        <>
          <BlinkDemo />
          <p>{t('intro.historyText')}</p>
        </>
      ),
    },
    {
      kicker: '2025 →',
      title: t('intro.spherexTitle'),
      body: (
        <>
          <SpectrumBar />
          <ul className="facts">
            <li>{t('intro.fact1')}</li>
            <li>{t('intro.fact2')}</li>
            <li>{t('intro.fact3')}</li>
          </ul>
          <p>{t('intro.spherexText')}</p>
        </>
      ),
    },
    {
      kicker: t('intro.toolsKicker'),
      title: t('intro.toolsTitle'),
      body: (
        <div className="tool-cards">
          <div className="tool-card">
            <span className="tool-icon">▣</span>
            <strong>{t('modes.original')}</strong>
            <p className="small muted">{t('intro.toolOriginal')}</p>
          </div>
          <div className="tool-card">
            <span className="tool-icon">⇔</span>
            <strong>{t('modes.swipe')}</strong>
            <p className="small muted">{t('intro.toolSwipe')}</p>
          </div>
        </div>
      ),
    },
    {
      kicker: t('intro.turnKicker'),
      title: t('intro.turnTitle'),
      body: (
        <>
          <p>{t('intro.turnText')}</p>
          <div className="row gap wrap">
            <button className="btn primary" onClick={onStartExploring}>
              {t('intro.startExploring')}
            </button>
            <button className="btn" onClick={onOpenGuide}>
              🧭 {t('intro.openGuide')}
            </button>
          </div>
        </>
      ),
    },
  ]
  const slide = slides[step]
  const last = step === slides.length - 1

  return (
    <Modal
      title={
        <span className="intro-title">
          <span className="kicker">{slide.kicker}</span>
          {slide.title}
        </span>
      }
      onClose={onClose}
      footer={
        <>
          <button className="btn ghost" onClick={onClose}>
            {t('intro.skip')}
          </button>
          <div className="dots">
            {slides.map((_, i) => (
              <button key={i} className={`dot ${i === step ? 'active' : ''}`} onClick={() => setStep(i)} aria-label={`${i + 1}`} />
            ))}
          </div>
          <div className="row gap">
            <button className="btn" onClick={() => setStep((s) => s - 1)} disabled={step === 0}>
              {t('intro.back')}
            </button>
            <button className="btn primary" onClick={() => (last ? onClose() : setStep((s) => s + 1))}>
              {last ? t('intro.finish') : t('intro.next')}
            </button>
          </div>
        </>
      }
    >
      <div className="intro-body">{slide.body}</div>
    </Modal>
  )
}
