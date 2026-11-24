import { MODULES } from '../modules.js'

const ICONS = {
  antena: <path d="M12 12v9M8 21h8M12 12a2 2 0 100-4 2 2 0 000 4zM7.5 6.5a6 6 0 000 7M16.5 6.5a6 6 0 010 7M4.7 4a10 10 0 000 12M19.3 4a10 10 0 010 12" />,
  adquisicion: <path d="M3 12h3l2.5-7 4 14 3-9 1.5 2H21" />,
  diferencial: <path d="M12 3v18M3 12h18M7 7l10 10M17 7L7 17" opacity=".9" />,
  informe: <path d="M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6" />,
}

export const Icon = ({ id, size = 19 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {ICONS[id]}
  </svg>
)

export default function Sidebar({ view, onChange, online, recording }) {
  return (
    <nav className="sidebar" aria-label="Módulos">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="2.2" /><path d="M5.6 5.6a9 9 0 000 12.8M18.4 5.6a9 9 0 010 12.8M8.5 8.5a4.8 4.8 0 000 7M15.5 8.5a4.8 4.8 0 010 7" />
          </svg>
        </span>
        <div>
          <strong>TwoMice-DGPS</strong>
          <small>Laboratorio satelital</small>
        </div>
      </div>
      <div className="nav-label">Módulos</div>
      <ul>
        {MODULES.map((m) => (
          <li key={m.id}>
            <button type="button" className={view === m.id ? 'active' : ''} aria-current={view === m.id ? 'page' : undefined} onClick={() => onChange(m.id)}>
              <Icon id={m.id} />
              <span>{m.label}</span>
              {!m.ready && <i className="dot" title="Pendiente" />}
            </button>
          </li>
        ))}
      </ul>
      <div className="side-foot">
        <div className="status"><span className={`pulse-dot ${online ? 'on' : ''}`} /><b>{online ? 'Backend conectado' : 'Backend sin conexión'}</b></div>
        <div className="status"><span className={`pulse-dot ${recording ? 'rec' : ''}`} />{recording ? 'Registrando sesión' : 'Sin sesión activa'}</div>
      </div>
    </nav>
  )
}
