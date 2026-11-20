import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import { MODULES } from './modules.js'
import { useAcquisition } from './hooks/useAcquisition.js'
import AcquisitionView from './views/AcquisitionView.jsx'
import AntennaView from './views/AntennaView.jsx'
import DifferentialView from './views/DifferentialView.jsx'
import ReportView from './views/ReportView.jsx'

export default function App() {
  const [view, setView] = useState('antena')
  const [units, setUnits] = useState({ 1: null, 2: null }) // análisis VNA por unidad; persisten al cambiar de módulo
  const [dgps, setDgps] = useState(null) // último resultado del diferencial
  const acq = useAcquisition() // la sesión en vivo persiste al cambiar de módulo
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
            <AntennaView units={units} setUnits={setUnits} />
          ) : view === 'adquisicion' ? (
            <AcquisitionView acq={acq} />
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
