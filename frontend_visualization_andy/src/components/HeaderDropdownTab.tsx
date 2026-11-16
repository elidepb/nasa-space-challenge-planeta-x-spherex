import { useRef, useEffect, type ReactNode } from 'react'

interface Props {
  label: string
  isOpen: boolean
  onToggle: () => void
  children: ReactNode
}

export function HeaderDropdownTab({ label, isOpen, onToggle, children }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onToggle()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onToggle])

  return (
    <div className={`header-dropdown-tab ${isOpen ? 'open' : ''}`} ref={containerRef}>
      <button
        type="button"
        className={`header-tab-trigger ${isOpen ? 'active' : ''}`}
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <span>{label}</span>
        <span className="dropdown-caret">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="header-dropdown-popover">
          {children}
        </div>
      )}
    </div>
  )
}
