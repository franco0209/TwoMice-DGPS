import { useState } from 'react'
import Plot from '../components/Plot.jsx'

const BAND_COLORS = {
  'GPS L5': '#8b5cf6', 'GPS L2': '#0ea5e9', 'GLONASS L2': '#14b8a6',
  'GPS L1': '#f59e0b', 'GLONASS L1': '#ef4444',
}

const bandShapes = (bands) =>
  Object.entries(bands).map(([name, b]) => ({
    type: 'line', x0: b.freq_mhz, x1: b.freq_mhz, yref: 'paper', y0: 0, y1: 1,
    line: { color: BAND_COLORS[name] ?? '#888', width: 1, dash: 'dot' },
  }))

const bandAnnotations = (bands) =>
  Object.entries(bands).map(([name, b]) => ({
    x: b.freq_mhz, yref: 'paper', y: 1, text: name, showarrow: false,
    textangle: -90, xanchor: 'right', yanchor: 'top',
    font: { size: 10, color: BAND_COLORS[name] },
  }))

function smithGrid() {
  const t = Array.from({ length: 181 }, (_, i) => (i * 2 * Math.PI) / 180)
  const circle = (cx, r) => ({
    x: t.map((a) => cx + r * Math.cos(a)), y: t.map((a) => r * Math.sin(a)),
    mode: 'lines', line: { color: '#9aa4b2', width: 0.6 }, hoverinfo: 'skip', showlegend: false,
  })
  const out = [circle(0, 1)]
  for (const r of [0.2, 0.5, 1, 2, 5]) out.push(circle(r / (1 + r), 1 / (1 + r)))
  return out
}

export default function AntennaView({ res, setRes }) {
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)

  async function upload(file) {
    if (!file) return
    setBusy(true)
    setErr('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await fetch('/api/vna/analyze', { method: 'POST', body: fd })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail ?? `Error ${r.status}`)
      setRes(j)
    } catch (e) {
      setErr(e instanceof TypeError ? 'No se pudo contactar al backend (¿uvicorn en :8000?)' : e.message)
    } finally {
      setBusy(false)
    }
  }

  const input = (
    <input type="file" accept=".s1p" hidden onChange={(e) => { upload(e.target.files[0]); e.target.value = '' }} />
  )

  return (
    <>
      {res ? (
        <div className="card filebar">
          <span>
            <strong>{res.filename}</strong>{' '}
            <span className="muted">· {res.freq_mhz.length} puntos · {res.freq_mhz[0].toFixed(0)}–{res.freq_mhz.at(-1).toFixed(0)} MHz</span>
          </span>
          <label className="btn">{busy ? 'Analizando…' : 'Cambiar archivo'}{input}</label>
        </div>
      ) : (
        <label
          className={`card drop ${over ? 'over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files[0]) }}
        >
          {input}
          {busy ? 'Analizando…' : 'Arrastre un archivo .s1p aquí o haga clic para seleccionarlo'}
        </label>
      )}
      {err && <p className="error">{err}</p>}
      {res && <Results r={res} />}
    </>
  )
}

function Kpis({ r }) {
  const bands = Object.entries(r.bands)
  const okCount = bands.filter(([, b]) => b.s11_db <= -10).length
  const best = r.resonances.reduce((a, x) => (!a || x.s11_db < a.s11_db ? x : a), null)
  const l1 = r.bands['GPS L1']
  const l2 = r.bands['GPS L2']
  const tone = (b) => (b.s11_db <= -10 ? 'ok' : 'bad')
  return (
    <div className="kpis">
      <div className="kpi">
        <span>Bandas adaptadas (−10 dB)</span>
        <strong>{okCount} / {bands.length}</strong>
        <small>dentro del barrido</small>
      </div>
      <div className="kpi">
        <span>Mejor resonancia</span>
        <strong>{best ? `${best.freq_mhz.toFixed(1)} MHz` : '—'}</strong>
        <small>{best ? `${best.s11_db.toFixed(1)} dB · VSWR ${best.vswr.toFixed(2)}` : 'sin resonancias'}</small>
      </div>
      <div className="kpi">
        <span>GPS L1 (1575,42 MHz)</span>
        <strong className={l1 ? tone(l1) : 'muted'}>{l1 ? `${l1.s11_db.toFixed(1)} dB` : 'fuera de barrido'}</strong>
        <small>{l1 ? `VSWR ${l1.vswr.toFixed(2)}` : ' '}</small>
      </div>
      <div className="kpi">
        <span>GPS L2 (1227,60 MHz)</span>
        <strong className={l2 ? tone(l2) : 'muted'}>{l2 ? `${l2.s11_db.toFixed(1)} dB` : 'fuera de barrido'}</strong>
        <small>{l2 ? `VSWR ${l2.vswr.toFixed(2)}` : ' '}</small>
      </div>
    </div>
  )
}

function Results({ r }) {
  const shapes = bandShapes(r.bands)
  const ann = bandAnnotations(r.bands)
  const xaxis = { title: { text: 'Frecuencia (MHz)' } }
  const flat = (v) => r.freq_mhz.map(() => v)
  const ref = { color: '#9aa4b2', dash: 'dash', width: 1 }
  return (
    <>
      <Kpis r={r} />
      <div className="grid2">
        <section className="card">
          <h2>S11 (dB)</h2>
          <Plot
            data={[
              { x: r.freq_mhz, y: r.s11_db, mode: 'lines', name: 'S11', line: { color: '#2563eb' } },
              { x: r.freq_mhz, y: flat(-10), mode: 'lines', name: '-10 dB', line: ref },
            ]}
            layout={{ xaxis, yaxis: { title: { text: 'dB' } }, shapes, annotations: ann }}
          />
        </section>
        <section className="card">
          <h2>VSWR</h2>
          <Plot
            data={[
              { x: r.freq_mhz, y: r.vswr, mode: 'lines', name: 'VSWR', line: { color: '#d97706' } },
              { x: r.freq_mhz, y: flat(2), mode: 'lines', name: 'VSWR 2', line: ref },
            ]}
            layout={{
              xaxis,
              yaxis: { title: { text: 'VSWR' }, range: [1, Math.min(10, Math.max(...r.vswr))] },
              shapes, annotations: ann,
            }}
          />
        </section>
        <section className="card">
          <h2>Carta de Smith (Γ)</h2>
          <Plot
            height={400}
            data={[
              ...smithGrid(),
              {
                x: r.gamma_real, y: r.gamma_imag, mode: 'lines', name: 'Γ',
                line: { color: '#2563eb', width: 2 },
                text: r.freq_mhz.map((f) => `${f.toFixed(1)} MHz`),
                hovertemplate: '%{text}<extra></extra>',
              },
            ]}
            layout={{
              showlegend: false,
              xaxis: { range: [-1.05, 1.05], scaleanchor: 'y', zeroline: false, showgrid: false },
              yaxis: { range: [-1.05, 1.05], zeroline: false, showgrid: false },
            }}
          />
        </section>
        <section className="card">
          <h2>Impedancia (Ω, Z0 = {r.z0})</h2>
          <Plot
            height={400}
            data={[
              { x: r.freq_mhz, y: r.z_real, mode: 'lines', name: 'R', line: { color: '#15803d' } },
              { x: r.freq_mhz, y: r.z_imag, mode: 'lines', name: 'X', line: { color: '#9333ea' } },
            ]}
            layout={{ xaxis, yaxis: { title: { text: 'Ω' } }, shapes }}
          />
        </section>
      </div>

      <section className="card">
        <h2>Bandas GNSS</h2>
        {Object.keys(r.bands).length === 0 ? (
          <p className="muted">El barrido no cubre ninguna banda GNSS.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Banda</th><th>Frecuencia (MHz)</th><th>S11 (dB)</th><th>VSWR</th><th>Estado</th></tr>
            </thead>
            <tbody>
              {Object.entries(r.bands).map(([n, b]) => {
                const ok = b.s11_db <= -10
                return (
                  <tr key={n}>
                    <td>{n}</td>
                    <td>{b.freq_mhz.toFixed(2)}</td>
                    <td>{b.s11_db.toFixed(1)}</td>
                    <td>{b.vswr.toFixed(2)}</td>
                    <td className={ok ? 'ok' : 'bad'}>{ok ? 'Adaptada' : 'Fuera de -10 dB'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Resonancias</h2>
        {r.resonances.length === 0 ? (
          <p className="muted">No se detectaron resonancias.</p>
        ) : (
          <table>
            <thead>
              <tr><th>f (MHz)</th><th>S11 (dB)</th><th>VSWR</th><th>Z (Ω)</th><th>BW -10 dB (MHz)</th><th>Cubre</th></tr>
            </thead>
            <tbody>
              {r.resonances.map((x) => (
                <tr key={x.freq_mhz}>
                  <td>{x.freq_mhz.toFixed(2)}</td>
                  <td>{x.s11_db.toFixed(1)}</td>
                  <td>{x.vswr.toFixed(2)}</td>
                  <td>{x.z_real.toFixed(1)} {x.z_imag < 0 ? '−' : '+'} j{Math.abs(x.z_imag).toFixed(1)}</td>
                  <td>{x.bw_mhz == null ? '—' : x.bw_mhz.toFixed(1)}</td>
                  <td>{x.covers.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}
