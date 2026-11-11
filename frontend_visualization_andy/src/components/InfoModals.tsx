import type { ReactNode } from 'react'
import type { MessageKey } from '../i18n'
import { useI18n } from '../i18n/I18nProvider'
import { Modal } from './Modal'

/* ---------------- Guía de campo ---------------- */

const A = 'fg-a'
const B = 'fg-b'

const GUIDE: { id: string; title: MessageKey; text: MessageKey; verdict: 'good' | 'bad' | 'maybe'; art: ReactNode }[] = [
  {
    id: 'mover',
    title: 'guide.moverTitle',
    text: 'guide.moverText',
    verdict: 'good',
    art: (
      <>
        <circle cx="25" cy="55" r="4" className={A} opacity="0.35" />
        <circle cx="50" cy="45" r="4" className={A} opacity="0.6" />
        <circle cx="75" cy="35" r="4" className={B} opacity="0.8" />
        <circle cx="100" cy="25" r="4" className={B} />
        <path d="M25 55 L100 25" className="fg-path" />
      </>
    ),
  },
  {
    id: 'ghost',
    title: 'guide.ghostTitle',
    text: 'guide.ghostText',
    verdict: 'bad',
    art: (
      <>
        <circle cx="45" cy="40" r="4" className={A} />
        <circle cx="80" cy="40" r="4" className="fg-empty" />
        <text x="80" y="62" textAnchor="middle" className="fg-text">
          ?
        </text>
      </>
    ),
  },
  {
    id: 'cosmic',
    title: 'guide.cosmicTitle',
    text: 'guide.cosmicText',
    verdict: 'bad',
    art: (
      <>
        <rect x="58" y="34" width="6" height="6" className="fg-hot" />
        <path d="M50 30 L72 48" className="fg-path" />
      </>
    ),
  },
  {
    id: 'variable',
    title: 'guide.variableTitle',
    text: 'guide.variableText',
    verdict: 'maybe',
    art: (
      <>
        <circle cx="40" cy="40" r="3" className={A} />
        <circle cx="85" cy="40" r="8" className={B} />
        <text x="62" y="44" textAnchor="middle" className="fg-text">
          →
        </text>
      </>
    ),
  },
  {
    id: 'dipole',
    title: 'guide.dipoleTitle',
    text: 'guide.dipoleText',
    verdict: 'good',
    art: (
      <>
        <path d="M62 30 A10 10 0 0 0 62 50 Z" className="fg-neg" />
        <path d="M62 30 A10 10 0 0 1 62 50 Z" className="fg-pos" />
      </>
    ),
  },
  {
    id: 'planetx',
    title: 'guide.planetXTitle',
    text: 'guide.planetXText',
    verdict: 'good',
    art: (
      <>
        <circle cx="25" cy="42" r="2.5" className={A} />
        <circle cx="100" cy="38" r="2.5" className={B} />
        <path d="M30 41 Q62 22 95 38" className="fg-path" />
        <text x="62" y="62" textAnchor="middle" className="fg-text small-svg">
          6 m
        </text>
      </>
    ),
  },
]

export function FieldGuideModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Modal title={`🧭 ${t('guide.title')}`} onClose={onClose} wide>
      <p className="muted">{t('guide.intro')}</p>
      <div className="legend small">
        <span>
          <i className="fg-dot a" /> {t('guide.legendA')}
        </span>
        <span>
          <i className="fg-dot b" /> {t('guide.legendB')}
        </span>
      </div>
      <div className="guide-grid">
        {GUIDE.map((g) => (
          <article key={g.id} className={`guide-card ${g.verdict}`}>
            <svg viewBox="0 0 125 75" className="guide-art">
              <rect width="125" height="75" rx="6" className="fg-bg" />
              {g.art}
            </svg>
            <h3>
              {t(g.title)} <span className={`verdict-tag ${g.verdict}`}>{t(`guide.verdict.${g.verdict}`)}</span>
            </h3>
            <p className="small muted">{t(g.text)}</p>
          </article>
        ))}
      </div>
    </Modal>
  )
}

/* ---------------- Atajos ---------------- */

const SHORTCUTS: [string, MessageKey][] = [
  ['← →', 'help.keys.epoch'],
  ['Space', 'help.keys.play'],
  ['O · B · D · S', 'help.keys.modes'],
  ['G', 'help.keys.grid'],
  ['K', 'help.keys.known'],
  ['F', 'help.keys.fullscreen'],
  ['?', 'help.keys.help'],
  ['Esc', 'help.keys.escape'],
]

export function HelpModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Modal title={`⌨ ${t('help.title')}`} onClose={onClose}>
      <table className="shortcuts">
        <tbody>
          {SHORTCUTS.map(([k, label]) => (
            <tr key={k}>
              <td>
                {k.split(' · ').map((part) => (
                  <kbd key={part}>{part}</kbd>
                ))}
              </td>
              <td>{t(label)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3 className="subtitle">{t('help.mouseTitle')}</h3>
      <ul className="small muted list">
        <li>{t('help.mouseWheel')}</li>
        <li>{t('help.mouseDrag')}</li>
        <li>{t('help.mouseClick')}</li>
        <li>{t('help.mouseDouble')}</li>
      </ul>
      <p className="note warn small">⚠ {t('help.photosensitivity')}</p>
    </Modal>
  )
}

/* ---------------- Créditos ---------------- */

const ACKNOWLEDGEMENT =
  'This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.'

export function AboutModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Modal title={`ⓘ ${t('about.title')}`} onClose={onClose} wide>
      <p>{t('about.intro')}</p>
      <p>
        <a href="https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/" target="_blank" rel="noreferrer">
          NASA Space Apps Challenge 2026 · Planet X and SPHEREx ↗
        </a>
      </p>

      <h3 className="subtitle">{t('about.team')}</h3>
      <ul className="team">
        <li>
          <strong>Elide</strong> · {t('about.roles.data')}
        </li>
        <li>
          <strong>Etner</strong> · {t('about.roles.science')}
        </li>
        <li>
          <strong>Anghelo</strong> · {t('about.roles.backend')}
        </li>
        <li>
          <strong>Andy</strong> · {t('about.roles.frontend')}
        </li>
        <li>
          <strong>Andre</strong> · {t('about.roles.video')}
        </li>
      </ul>

      <h3 className="subtitle">{t('about.data')}</h3>
      <p className="small">{t('about.dataText')}</p>
      <blockquote className="ack small">{ACKNOWLEDGEMENT}</blockquote>
      <ul className="small list">
        <li>
          SPHEREx QR2 · DOI{' '}
          <a href="https://doi.org/10.26131/IRSA652" target="_blank" rel="noreferrer">
            10.26131/IRSA652
          </a>
        </li>
        <li>
          SPHEREx QR3 · DOI{' '}
          <a href="https://doi.org/10.26131/IRSA662" target="_blank" rel="noreferrer">
            10.26131/IRSA662
          </a>
        </li>
      </ul>
      <p className="note warn small">{t('about.mockNote')}</p>

      <h3 className="subtitle">{t('about.inspiration')}</h3>
      <ul className="small list">
        <li>
          <a href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">
            NASA/IPAC IRSA · SPHEREx
          </a>
        </li>
        <li>
          <a href="https://science.nasa.gov/citizen-science/backyard-worlds-planet-9/" target="_blank" rel="noreferrer">
            Backyard Worlds: Planet 9
          </a>{' '}
          ·{' '}
          <a href="https://github.com/backyardworlds/wiseview" target="_blank" rel="noreferrer">
            WiseView
          </a>
        </li>
        <li>
          <a href="https://ssp.imcce.fr/webservices/skybot/" target="_blank" rel="noreferrer">
            IMCCE SkyBoT
          </a>{' '}
          ·{' '}
          <a href="https://simbad.cds.unistra.fr/simbad/" target="_blank" rel="noreferrer">
            CDS SIMBAD
          </a>
        </li>
      </ul>
    </Modal>
  )
}
