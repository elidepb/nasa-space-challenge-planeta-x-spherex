import type { AnalysisPhase } from '../hooks/useAnalysis'
import type { MessageKey } from '../i18n'
import { useI18n } from '../i18n/I18nProvider'

interface Props {
  phase: AnalysisPhase
  progress?: number
  message?: string
  error?: string | null
  onRetry?: () => void
}

const PHASE_TEXT: Partial<Record<AnalysisPhase, MessageKey>> = {
  submitting: 'status.phases.submitting',
  pending: 'status.phases.pending',
  processing: 'status.phases.processing',
  'loading-results': 'status.phases.loadingResults',
}

export function StatusView({ phase, progress, message, error, onRetry }: Props) {
  const { t } = useI18n()

  if (phase === 'idle') {
    return (
      <div className="status">
        <div className="status-icon">✦</div>
        <h3>{t('status.idleTitle')}</h3>
        <p className="muted">{t('status.idleText')}</p>
      </div>
    )
  }
  if (phase === 'error') {
    return (
      <div className="status error">
        <div className="status-icon">!</div>
        <h3>{t('status.errorTitle')}</h3>
        <p className="muted">{error ?? t('status.unknownError')}</p>
        {onRetry && (
          <button className="btn" onClick={onRetry}>
            {t('status.retry')}
          </button>
        )}
      </div>
    )
  }
  if (phase === 'completed') {
    return (
      <div className="status">
        <div className="status-icon">∅</div>
        <h3>{t('status.emptyTitle')}</h3>
        <p className="muted">{t('status.emptyText')}</p>
      </div>
    )
  }
  const phaseKey = PHASE_TEXT[phase]
  return (
    <div className="status">
      <div className="spinner" />
      {phaseKey && <h3>{t(phaseKey)}</h3>}
      {message && <p className="muted">{message}</p>}
      {progress !== undefined && (
        <div className="progress">
          <div className="progress-bar" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      )}
    </div>
  )
}
