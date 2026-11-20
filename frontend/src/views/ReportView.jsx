import { useEffect, useState } from 'react'

const f = (v, d = 2) => (v == null ? '—' : v.toFixed(d))

function download(blob, name) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

export default function ReportView({ result, units }) {
  const [list, setList] = useState([])
  const [err, setErr] = useState('')
  const [withVna, setWithVna] = useState(true)
  const vna = units[1] || units[2]

  const load = () => fetch('/api/analysis/experiments').then((r) => r.json()).then(setList)
    .catch(() => setErr('No se pudo contactar al backend'))
  useEffect(() => { load() }, [])

  async function pdfCurrent() {
    setErr('')
    try {
      const fd = new FormData()
      fd.append('result', new Blob([JSON.stringify(result)], { type: 'application/json' }), 'result.json')
      if (withVna && vna) fd.append('vna', new Blob([JSON.stringify(vna)], { type: 'application/json' }), 'vna.json')
      const r = await fetch('/api/reports/pdf', { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `Error ${r.status}`)
      download(await r.blob(), 'informe-twomice-dgps.pdf')
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <>
      <section className="card">
        <h2>Informe del análisis actual</h2>
        {result ? (
          <>
            <p className="muted">
              CEP50 {f(result.before.cep50)} → {f(result.after.cep50)} m · mejora {f(result.improvement.cep50, 0)} % ·
              {' '}{result.epochs.same_sats} épocas usadas{result.accuracy ? '' : ' · solo precisión'}
            </p>
            <div className="ctrl-head">
              <button className="btn-primary" onClick={pdfCurrent}>Descargar PDF</button>
              <button className="btn" onClick={() => download(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }), 'analisis.json')}>JSON</button>
              <label className="muted">
                <input type="checkbox" checked={withVna && !!vna} disabled={!vna} onChange={(e) => setWithVna(e.target.checked)} />
                {' '}Incluir S11/VSWR de la antena {vna ? '' : '(cargue un .s1p en Antena)'}
              </label>
            </div>
          </>
        ) : (
          <p className="muted">Calcule un diferencial en el módulo Diferencial para generar el informe.</p>
        )}
        {err && <p className="error">{err}</p>}
      </section>

      <section className="card">
        <h2>Historial de experimentos</h2>
        {list.length === 0 ? (
          <p className="muted">Aún no hay sesiones guardadas. Se crean desde Adquisición.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Sesión</th><th>Modo</th><th>Épocas ref/móvil</th><th>CEP50 1rx → DGPS (m)</th><th>Mejora CEP50</th><th>Mismo conjunto</th><th>Descargas</th></tr>
            </thead>
            <tbody>
              {list.map((s) => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td>{s.mode}</td>
                  <td>{s.epochs ? `${s.epochs.ref} / ${s.epochs.rover}` : '—'}</td>
                  <td>{s.summary ? `${f(s.summary.cep50_before)} → ${f(s.summary.cep50_after)}` : 'sin analizar'}</td>
                  <td>{s.summary ? `${f(s.summary.improvement.cep50, 0)} %` : '—'}</td>
                  <td>{s.summary ? `${f(s.summary.same_sats_pct, 0)} %` : '—'}</td>
                  <td>
                    {s.summary ? (
                      <>
                        <a href={`/api/reports/sessions/${s.id}.pdf`}>PDF</a>{' · '}
                        <a href={`/api/analysis/sessions/${s.id}/export?fmt=csv`}>CSV</a>{' · '}
                        <a href={`/api/analysis/sessions/${s.id}/export?fmt=json`}>JSON</a>
                      </>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button className="btn" onClick={load}>Actualizar</button>
      </section>
    </>
  )
}
