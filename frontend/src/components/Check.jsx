/** Fila de validación: estado + mensaje + acción. */
export default function Check({ state, title, detail, action }) {
  const icon = { ok: '✓', fail: '✕', run: '…', idle: '○' }[state]
  return (
    <div className={`check ${state}`}>
      <span className="check-icon">{icon}</span>
      <div className="check-body">
        <strong>{title}</strong>
        {detail && <small>{detail}</small>}
      </div>
      {action}
    </div>
  )
}

