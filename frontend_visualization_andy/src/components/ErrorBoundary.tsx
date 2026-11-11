import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Evita pantalla negra total si un hijo lanza durante el render. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI crash', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="error-boundary panel" role="alert">
        <h2 className="panel-title">La interfaz falló al renderizar</h2>
        <p className="muted small">{this.state.error.message}</p>
        <button type="button" className="btn primary" onClick={() => this.setState({ error: null })}>
          Reintentar
        </button>
        <button type="button" className="btn" onClick={() => window.location.assign(window.location.pathname)}>
          Recargar limpio
        </button>
      </div>
    )
  }
}
