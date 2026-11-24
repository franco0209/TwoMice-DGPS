import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import { MODULES } from './modules.js'
import { useAcquisition } from './hooks/useAcquisition.js'
import AcquisitionView from './views/AcquisitionView.jsx'
import AntennaView from './views/AntennaView.jsx'
import DifferentialView from './views/DifferentialView.jsx'
import ReportView from './views/ReportView.jsx'

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') || 'auto' } catch { return 'auto' }
  })
  useEffect(() => {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('theme', theme) } catch { /* sin almacenamiento */ }
  }, [theme])
  const isDark = theme === 'dark' || (theme === 'auto' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  return [isDark, () => setTheme(isDark ? 'light' : 'dark')]
}

export default function App() {
  const [isDark, toggleTheme] = useTheme()
  const [view, setView] = useState('antena')
  const [units, setUnits] = useState({ 1: null, 2: null }) // análisis VNA por unidad; persisten al cambiar de módulo
  const [dgps, setDgps] = useState(null) // último resultado del diferencial
  const acq = useAcquisition() // la sesión en vivo persiste al cambiar de módulo
  const current = MODULES.find((m) => m.id === view)

  return (
    <div className="shell">
      <Sidebar view={view} onChange={setView} online={acq.online} recording={acq.status?.state === 'running'} />
      <div className="content">
        <header className="topbar">
          <div>
            <h1>{current.label}</h1>
            <p>{current.subtitle}</p>
          </div>
          <div className="top-actions">
            {acq.status?.state === 'running' && (
              <span className="pill"><span className="pulse-dot rec" />REC · {Math.round(acq.status.elapsed_s)} s</span>
            )}
            {!current.ready && <span className="badge">Pendiente</span>}
            <button type="button" className="icon-btn" onClick={toggleTheme} title={isDark ? 'Modo claro' : 'Modo oscuro'} aria-label="Cambiar tema">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                {isDark ? <path d="M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3L4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4M12 8a4 4 0 100 8 4 4 0 000-8z" /> : <path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z" />}
              </svg>
            </button>
          </div>
        </header>
        <main key={view}>
          {view === 'antena' ? (
            <AntennaView units={units} setUnits={setUnits} />
          ) : view === 'adquisicion' ? (
            <AcquisitionView acq={acq} onNavigate={setView} />
          ) : view === 'diferencial' ? (
            <DifferentialView result={dgps} setResult={setDgps} />
          ) : (
            <ReportView result={dgps} units={units} />
          )}
        </main>
      </div>
    </div>
  )
}
