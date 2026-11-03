import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import { MODULES } from './modules.js'
import AntennaView from './views/AntennaView.jsx'
import Placeholder from './views/Placeholder.jsx'

export default function App() {
  const [view, setView] = useState('antena')
  const [vna, setVna] = useState(null) // el análisis persiste al cambiar de módulo
  const current = MODULES.find((m) => m.id === view)

  return (
    <div className="shell">
      <Sidebar view={view} onChange={setView} />
      <div className="content">
        <header className="topbar">
          <div>
            <h1>{current.label}</h1>
            <p>{current.subtitle}</p>
          </div>
          {!current.ready && <span className="badge">Pendiente</span>}
        </header>
        <main>
          {view === 'antena' ? (
            <AntennaView res={vna} setRes={setVna} />
          ) : (
            <Placeholder module={current} />
          )}
        </main>
      </div>
    </div>
  )
}
