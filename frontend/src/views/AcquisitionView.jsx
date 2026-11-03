import { useEffect, useMemo, useState } from 'react'
import Plot from '../components/Plot.jsx'

const RX = { ref: { label: 'Referencia', color: '#2563eb' }, rover: { label: 'Móvil', color: '#f59e0b' } }
const fmt = (v, d = 1) => (v == null ? '—' : v.toFixed(d))

async function api(path, opts) {
  const r = await fetch(path, opts)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `Error ${r.status}`)
  return j
}

function Controls({ status, online, onStart, onStop }) {
  const [mode, setMode] = useState('sim')
  const [sim, setSim] = useState({ duration_s: 600, speed: 10, baseline_m: 3, rover_cn0_offset_db: 0, seed: 1 })
  const [ports, setPorts] = useState([])
  const [real, setReal] = useState({ ref: '', rover: '', baud: 9600, duration_s: 3600 })
  const [err, setErr] = useState('')
  const running = status?.state === 'running'

  useEffect(() => {
    if (mode === 'real') api('/api/gps/ports').then(setPorts).catch((e) => setErr(e.message))
  }, [mode])

  const num = (obj, set, k) => ({
    value: obj[k], onChange: (e) => set({ ...obj, [k]: Number(e.target.value) }), disabled: running, type: 'number',
  })

  async function start() {
    setErr('')
    try {
      const body = mode === 'sim'
        ? { mode, duration_s: sim.duration_s, speed: sim.speed,
            sim: { seed: sim.seed, baseline_m: sim.baseline_m, rover_cn0_offset_db: sim.rover_cn0_offset_db } }
        : { mode, duration_s: real.duration_s,
            ref: { port: real.ref, baud: real.baud }, rover: { port: real.rover, baud: real.baud } }
      await onStart(body)
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <section className="card">
      <div className="ctrl-head">
        <div className="seg">
          {[['sim', 'Simulación'], ['real', 'Real (puertos serie)']].map(([k, l]) => (
            <button key={k} className={mode === k ? 'on' : ''} disabled={running} onClick={() => setMode(k)}>{l}</button>
          ))}
        </div>
        <span className="muted">
          {online ? 'Conectado' : 'Sin conexión al backend'}
          {status && ` · sesión ${status.state === 'running' ? 'en curso' : 'finalizada'} (${status.mode})`}
        </span>
        <div className="ctrl-actions">
          {running
            ? <button className="btn-primary stop" onClick={onStop}>Detener</button>
            : <button className="btn-primary" disabled={!online} onClick={start}>Iniciar</button>}
        </div>
      </div>

      {mode === 'sim' ? (
        <div className="fields">
          <label>Duración (s)<input {...num(sim, setSim, 'duration_s')} min="10" /></label>
          <label>Velocidad (×, 0 = máxima)<input {...num(sim, setSim, 'speed')} min="0" /></label>
          <label>Línea base (m)<input {...num(sim, setSim, 'baseline_m')} min="0.1" step="0.5" /></label>
          <label>C/N0 móvil (dB)<input {...num(sim, setSim, 'rover_cn0_offset_db')} step="0.5" /></label>
          <label>Semilla<input {...num(sim, setSim, 'seed')} /></label>
        </div>
      ) : (
        <div className="fields">
          {['ref', 'rover'].map((k) => (
            <label key={k}>Puerto {RX[k].label.toLowerCase()}
              <select value={real[k]} disabled={running} onChange={(e) => setReal({ ...real, [k]: e.target.value })}>
                <option value="">— elegir —</option>
                {ports.map((p) => <option key={p.port} value={p.port}>{p.port} · {p.description}</option>)}
              </select>
            </label>
          ))}
          <label>Baudios<input {...num(real, setReal, 'baud')} /></label>
          <label>Duración (s)<input {...num(real, setReal, 'duration_s')} min="10" /></label>
        </div>
      )}
      {mode === 'sim' && (
        <p className="muted note">
          Simulación a nivel de pseudorango: los errores comunes (efemérides, iono, tropo) y los independientes
          (multitrayecto, ruido, selección de satélites) producen el NMEA que entraría por el puerto serie.
          La constelación es sintética, no el cielo real de la fecha.
        </p>
      )}
      {(err || status?.error) && <p className="error">{err || status.error}</p>}
    </section>
  )
}

function Kpis({ hist }) {
  const last = { ref: hist.ref.at(-1), rover: hist.rover.at(-1) }
  const common = useMemo(() => {
    const m = new Map(hist.ref.filter((e) => e.quality > 0).map((e) => [e.utc, e]))
    let both = 0
    let same = 0
    for (const e of hist.rover) {
      const r = m.get(e.utc)
      if (r && e.quality > 0) {
        both++
        const a = new Set(r.sats_used)
        if (a.size === e.sats_used.length && e.sats_used.every((s) => a.has(s))) same++
      }
    }
    return { both, same }
  }, [hist])
  const shared = (() => {
    const a = last.ref?.sats_used ?? []
    const b = new Set(last.rover?.sats_used ?? [])
    return a.filter((s) => b.has(s)).length
  })()
  return (
    <div className="kpis">
      {Object.entries(RX).map(([k, v]) => {
        const e = last[k]
        return (
          <div className="kpi" key={k}>
            <span style={{ color: v.color }}>● {v.label}</span>
            <strong className={e ? (e.quality > 0 ? 'ok' : 'bad') : 'muted'}>
              {e ? (e.quality > 0 ? `Fix 3D · ${e.nsats} sat` : 'Sin fix') : 'Sin datos'}
            </strong>
            <small>HDOP {fmt(e?.hdop)} · {e?.utc ? e.utc.slice(11, 19) + ' UTC' : '—'}</small>
          </div>
        )
      })}
      <div className="kpi">
        <span>Satélites en común (ahora)</span>
        <strong>{shared} / {last.ref?.sats_used.length ?? 0}</strong>
        <small>usados por ref y móvil a la vez</small>
      </div>
      <div className="kpi">
        <span>Épocas con mismo conjunto</span>
        <strong>{common.both ? `${((100 * common.same) / common.both).toFixed(0)} %` : '—'}</strong>
        <small>{common.both} épocas comparadas · condición del diferencial</small>
      </div>
    </div>
  )
}

function Charts({ hist }) {
  const last = { ref: hist.ref.at(-1), rover: hist.rover.at(-1) }
  const sky = Object.entries(RX).map(([k, v]) => {
    const sats = (last[k]?.sats_view ?? []).filter((s) => s.el != null && s.az != null)
    return {
      type: 'scatterpolar', mode: 'markers+text', name: v.label,
      r: sats.map((s) => 90 - s.el), theta: sats.map((s) => s.az),
      text: sats.map((s) => s.id.slice(2)), textposition: k === 'ref' ? 'top center' : 'bottom center',
      textfont: { size: 9 },
      marker: {
        size: 10, symbol: k === 'ref' ? 'circle' : 'diamond-open',
        color: v.color, opacity: sats.map((s) => (s.snr == null ? 0.25 : 1)),
        line: { width: 1.5, color: v.color },
      },
      hovertemplate: sats.map((s) => `${s.id} · el ${s.el}° · az ${s.az}° · SNR ${s.snr ?? '—'}<extra>${v.label}</extra>`),
    }
  })

  const ids = [...new Set(Object.keys(RX).flatMap((k) => (last[k]?.sats_view ?? []).map((s) => s.id)))].sort()
  const snr = Object.entries(RX).map(([k, v]) => ({
    type: 'bar', name: v.label, x: ids.map((i) => i.slice(2)),
    y: ids.map((i) => last[k]?.sats_view.find((s) => s.id === i)?.snr ?? null),
    marker: { color: v.color },
  }))

  const scatter = Object.entries(RX).map(([k, v]) => {
    const pts = hist[k].filter((e) => e.quality > 0)
    if (!pts.length) return { x: [], y: [], mode: 'markers', name: v.label }
    const lat0 = pts.reduce((a, e) => a + e.lat, 0) / pts.length
    const lon0 = pts.reduce((a, e) => a + e.lon, 0) / pts.length
    const kE = 111320 * Math.cos((lat0 * Math.PI) / 180)
    return {
      x: pts.map((e) => (e.lon - lon0) * kE), y: pts.map((e) => (e.lat - lat0) * 110574),
      mode: 'markers', name: v.label, marker: { size: 5, color: v.color, opacity: 0.55 },
    }
  })

  return (
    <div className="grid2">
      <section className="card">
        <h2>Skyplot (último instante)</h2>
        <Plot
          data={sky}
          height={380}
          layout={{
            margin: { l: 30, r: 30, t: 20, b: 40 },
            polar: {
              bgcolor: 'rgba(0,0,0,0)',
              radialaxis: { range: [0, 90], tickvals: [0, 30, 60, 90], ticktext: ['90°', '60°', '30°', '0°'], angle: 90, tickfont: { size: 9 } },
              angularaxis: { direction: 'clockwise', rotation: 90, tickvals: [0, 90, 180, 270], ticktext: ['N', 'E', 'S', 'O'] },
            },
          }}
        />
        <p className="muted note">Opacidad baja = en vista pero sin rastrear (sin SNR).</p>
      </section>
      <section className="card">
        <h2>SNR por satélite (dB-Hz)</h2>
        <Plot
          data={snr}
          height={380}
          layout={{ barmode: 'group', xaxis: { title: { text: 'PRN' }, type: 'category' }, yaxis: { title: { text: 'dB-Hz' }, range: [0, 55] } }}
        />
      </section>
      <section className="card">
        <h2>Dispersión de posición (m, respecto a la media de cada receptor)</h2>
        <Plot
          data={scatter}
          height={380}
          layout={{
            xaxis: { title: { text: 'Este (m)' } },
            yaxis: { title: { text: 'Norte (m)' }, scaleanchor: 'x' },
          }}
        />
      </section>
      <section className="card">
        <h2>Satélites usados y HDOP</h2>
        <Plot
          data={Object.entries(RX).flatMap(([k, v]) => [
            { x: hist[k].map((e) => e.utc), y: hist[k].map((e) => e.nsats), mode: 'lines', name: `${v.label} · sat`, line: { color: v.color, width: 1.5 } },
            { x: hist[k].map((e) => e.utc), y: hist[k].map((e) => e.hdop), mode: 'lines', name: `${v.label} · HDOP`, yaxis: 'y2', line: { color: v.color, width: 1, dash: 'dot' } },
          ])}
          height={380}
          layout={{
            yaxis: { title: { text: 'Satélites' } },
            yaxis2: { title: { text: 'HDOP' }, overlaying: 'y', side: 'right', showgrid: false, range: [0, 5] },
          }}
        />
      </section>
    </div>
  )
}

export default function AcquisitionView({ acq }) {
  const { hist, status, online, reset } = acq
  const started = hist.ref.length + hist.rover.length > 0

  async function start(body) {
    reset()
    await api('/api/gps/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  }
  const stop = () => api('/api/gps/sessions/current/stop', { method: 'POST' }).catch(() => {})

  return (
    <>
      <Controls status={status} online={online} onStart={start} onStop={stop} />
      {started ? (
        <>
          <Kpis hist={hist} />
          <Charts hist={hist} />
        </>
      ) : (
        <section className="card empty"><p className="muted">Inicie una sesión para ver los receptores en vivo.</p></section>
      )}
    </>
  )
}
