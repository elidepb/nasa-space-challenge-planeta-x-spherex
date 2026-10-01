import { useEffect, useRef } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import type { EpochImage, ObservationSummary } from '../types/contracts'

interface Props {
  observations: ObservationSummary[]
  epochs: EpochImage[]
  activeIndex: number
  referenceIndex: number
  markedIds: Set<string>
  onSelect: (index: number) => void
}

export function Filmstrip({ observations, epochs, activeIndex, referenceIndex, markedIds, onSelect }: Props) {
  const { t } = useI18n()
  const activeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [activeIndex])

  if (observations.length === 0) return null
  const urlFor = (id: string) => epochs.find((e) => e.observationId === id)?.url

  return (
    <div className="filmstrip" role="listbox" aria-label={t('filmstrip.label')}>
      {observations.map((o, i) => (
        <button
          key={o.id}
          ref={i === activeIndex ? activeRef : undefined}
          className={`thumb ${i === activeIndex ? 'active' : ''} ${i === referenceIndex ? 'ref' : ''}`}
          onClick={() => onSelect(i)}
          title={`${t('timeline.epochTitle', { n: i + 1, date: o.timestamp })}`}
          role="option"
          aria-selected={i === activeIndex}
        >
          {urlFor(o.id) && <img src={urlFor(o.id)} alt="" draggable={false} />}
          <span className="thumb-n">{i + 1}</span>
          {i === referenceIndex && <span className="thumb-tag">{t('observations.reference')}</span>}
          {markedIds.has(o.id) && <span className="thumb-mark">◎</span>}
        </button>
      ))}
    </div>
  )
}
