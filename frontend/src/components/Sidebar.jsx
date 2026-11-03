import { MODULES } from '../modules.js'

export default function Sidebar({ view, onChange }) {
  return (
    <nav className="sidebar" aria-label="Módulos">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <div>
          <strong>TwoMice-DGPS</strong>
          <small>Laboratorio satelital</small>
        </div>
      </div>
      <ul>
        {MODULES.map((m) => (
          <li key={m.id}>
            <button
              type="button"
              className={view === m.id ? 'active' : ''}
              aria-current={view === m.id ? 'page' : undefined}
              onClick={() => onChange(m.id)}
            >
              <span>{m.label}</span>
              {!m.ready && <i className="dot" title="Pendiente" />}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
