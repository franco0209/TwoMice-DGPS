export default function Placeholder({ module }) {
  return (
    <section className="card empty">
      <h2>Módulo en desarrollo</h2>
      <p className="muted">Este módulo incluirá:</p>
      <ul>
        {module.planned.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </section>
  )
}
