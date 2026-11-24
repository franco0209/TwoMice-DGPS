import { useCallback, useEffect, useRef, useState } from 'react'
import { api, Charts, fmt, Kpis, RX } from './AcquisitionLive.jsx'

const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const probe = (port, baud, seconds = 3) => post('/api/gps/probe', { port, baud, seconds })

/** Fila de validación: estado + mensaje + acción. */
function Check({ state, title, detail, action }) {
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

function Stepper({ steps, current, maxReached, onGo }) {
  return (
    <ol className="stepper">
      {steps.map((s, i) => (
        <li key={s.id} className={i === current ? 'cur' : i < maxReached ? 'done' : ''}>
          <button disabled={i > maxReached} onClick={() => onGo(i)}>
            <span className="num">{i < maxReached && i !== current ? '✓' : i + 1}</span>{s.label}
          </button>
        </li>
      ))}
    </ol>
  )
}

function StepMode({ w, set }) {
  return (
    <>
      <p>Elija el origen de los datos. En <b>real</b> el asistente lo guía para conectar y validar cada receptor antes de registrar.</p>
      <div className="choices">
        {[['real', 'Receptores reales', 'Dos receptores NMEA por puerto serie/USB (referencia + móvil).'],
          ['sim', 'Simulación', 'Pseudorangos sintéticos; no requiere hardware. Útil para practicar y validar el análisis.']].map(([k, t, d]) => (
          <button key={k} className={`choice ${w.mode === k ? 'on' : ''}`} onClick={() => set({ mode: k })}>
            <strong>{t}</strong><small>{d}</small>
          </button>
        ))}
      </div>
    </>
  )
}

function StepBackend({ online }) {
  return (
    <>
      <p>Verifique que la interfaz alcanza al backend (puerto 8000) por WebSocket.</p>
      <Check state={online ? 'ok' : 'fail'} title="Conexión con el backend"
        detail={online ? 'WebSocket abierto.' : 'Sin conexión. Inicie el backend desde /backend: uvicorn app.main:app --port 8000. Se reintenta solo.'} />
    </>
  )
}

function StepPorts({ w, set }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const scan = useCallback(async () => {
    setBusy(true); setErr('')
    try { set({ ports: await api('/api/gps/ports') }) } catch (e) { setErr(e.message) }
    setBusy(false)
  }, [set])
  useEffect(() => { scan() }, [scan])
  const n = w.ports.length
  return (
    <>
      <ol className="todo">
        <li>Alimente y conecte los <b>dos</b> receptores a la PC (USB o adaptador serie).</li>
        <li>Ponga el <b>referencia</b> en la posición conocida y el <b>móvil</b> a la distancia de línea base prevista, con las antenas a cielo abierto.</li>
        <li>Pulse «Buscar puertos»: debe aparecer un puerto por receptor.</li>
      </ol>
      <Check state={busy ? 'run' : n >= 2 ? 'ok' : 'fail'} title={`Puertos detectados: ${n}`}
        detail={err || (n >= 2 ? w.ports.map((p) => `${p.port} (${p.description})`).join(' · ')
          : n === 1 ? 'Solo hay un puerto: falta un receptor (cable, driver USB-serie o alimentación).'
          : 'No hay puertos. Revise cables y el driver del adaptador (Administrador de dispositivos → Puertos COM).')}
        action={<button className="btn-sec" disabled={busy} onClick={scan}>Buscar puertos</button>} />
    </>
  )
}

function StepNmea({ w, set }) {
  const [busy, setBusy] = useState(false)
  const same = Boolean(w.ref) && w.ref === w.rover
  const run = async () => {
    setBusy(true)
    const res = {}
    await Promise.all(['ref', 'rover'].map(async (k) => {
      try { res[k] = await probe(w[k], w.baud) } catch (e) { res[k] = { ok: false, message: e.message } }
    }))
    set({ nmea: res })
    setBusy(false)
  }
  return (
    <>
      <p>Asigne cada puerto y compruebe que entra NMEA válido (se abre el puerto ~3 s y se verifica el checksum de cada sentencia).</p>
      <div className="fields">
        {['ref', 'rover'].map((k) => (
          <label key={k}>Puerto {RX[k].label.toLowerCase()}
            <select value={w[k]} onChange={(e) => set({ [k]: e.target.value, nmea: {}, fix: {} })}>
              <option value="">— elegir —</option>
              {w.ports.map((p) => <option key={p.port} value={p.port}>{p.port} · {p.description}</option>)}
            </select>
          </label>
        ))}
        <label>Baudios
          <select value={w.baud} onChange={(e) => set({ baud: Number(e.target.value), nmea: {}, fix: {} })}>
            {[4800, 9600, 19200, 38400, 57600, 115200].map((b) => <option key={b}>{b}</option>)}
          </select>
        </label>
      </div>
      {same && <p className="error">Referencia y móvil deben usar puertos distintos.</p>}
      <div className="checks">
        {['ref', 'rover'].map((k) => {
          const r = w.nmea[k]
          return (
            <Check key={k} state={busy ? 'run' : !r ? 'idle' : r.ok ? 'ok' : 'fail'}
              title={`${RX[k].label}: ${r?.ok ? 'NMEA válido' : 'NMEA'}`}
              detail={!r ? 'Sin probar.' : r.ok
                ? `${r.sentences.join(', ')} · ${r.good} sentencias válidas, ${r.bad} con error`
                : r.message} />
          )
        })}
      </div>
      <div className="row">
        <button className="btn-sec" disabled={busy || same || !w.ref || !w.rover} onClick={run}>
          {busy ? 'Comprobando…' : 'Comprobar NMEA'}
        </button>
      </div>
    </>
  )
}

const hasFix = (r) => Boolean(r?.ok && r.quality > 0 && r.nsats >= 4)

function StepFix({ w, set }) {
  const [busy, setBusy] = useState(false)
  const [auto, setAuto] = useState(true)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const both = hasFix(w.fix.ref) && hasFix(w.fix.rover)

  const run = useCallback(async () => {
    setBusy(true)
    const res = {}
    await Promise.all(['ref', 'rover'].map(async (k) => {
      try { res[k] = await probe(w[k], w.baud, 4) } catch (e) { res[k] = { ok: false, message: e.message } }
    }))
    if (alive.current) { set({ fix: res }); setBusy(false) }
  }, [w.ref, w.rover, w.baud, set])

  useEffect(() => {
    if (!auto || both || busy) return undefined
    const t = setTimeout(run, w.fix.ref ? 1500 : 0)
    return () => clearTimeout(t)
  }, [auto, both, busy, run, w.fix.ref])

  return (
    <>
      <p>Los receptores necesitan unos minutos a cielo abierto para el primer fix (arranque en frío ≈ 1 min o más). Se re-comprueba solo hasta que ambos tengan <b>fix y ≥ 4 satélites</b>.</p>
      <div className="checks">
        {['ref', 'rover'].map((k) => {
          const r = w.fix[k]
          return (
            <Check key={k} state={!r ? 'run' : hasFix(r) ? 'ok' : busy ? 'run' : 'fail'}
              title={`${RX[k].label}: ${!r ? 'comprobando…' : hasFix(r) ? 'fix obtenido' : 'sin fix todavía'}`}
              detail={r ? (r.ok ? `Calidad GGA ${r.quality} · ${r.nsats} sat usados · ${r.sats_tracked} rastreados · HDOP ${fmt(r.hdop)}` : r.message) : ''} />
          )
        })}
      </div>
      <div className="row">
        <button className="btn-sec" disabled={busy} onClick={run}>Comprobar ahora</button>
        <label className="inline"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Re-comprobar automáticamente</label>
      </div>
      {!both && <p className="muted note">Puede continuar sin fix, pero las épocas sin fix no entran al análisis.</p>}
    </>
  )
}

function StepSim({ w, set }) {
  const num = (k, extra = {}) => ({ type: 'number', value: w.sim[k], ...extra,
    onChange: (e) => set({ sim: { ...w.sim, [k]: Number(e.target.value) } }) })
  return (
    <>
      <p>Defina el escenario. Los errores comunes se cancelan en el diferencial; los independientes (multitrayecto, ruido, selección de satélites) no.</p>
      <div className="fields">
        <label>Duración (s)<input {...num('duration_s', { min: 10 })} /></label>
        <label>Velocidad (×, 0 = máxima)<input {...num('speed', { min: 0 })} /></label>
        <label>Línea base (m)<input {...num('baseline_m', { min: 0.1, step: 0.5 })} /></label>
        <label>C/N0 móvil (dB)<input {...num('rover_cn0_offset_db', { step: 0.5 })} /></label>
        <label>Semilla<input {...num('seed')} /></label>
      </div>
      <p className="muted note">La constelación es sintética, no el cielo real de la fecha.</p>
    </>
  )
}

function StepRun({ w, set, acq, online }) {
  const { hist, status } = acq
  const [err, setErr] = useState('')
  const running = status?.state === 'running'
  const real = w.mode === 'real'
  const dur = real ? w.duration_s : w.sim.duration_s

  async function start() {
    setErr('')
    acq.reset()
    try {
      await post('/api/gps/sessions', real
        ? { mode: 'real', duration_s: w.duration_s, ref: { port: w.ref, baud: w.baud }, rover: { port: w.rover, baud: w.baud } }
        : { mode: 'sim', duration_s: w.sim.duration_s, speed: w.sim.speed,
            sim: { seed: w.sim.seed, baseline_m: w.sim.baseline_m, rover_cn0_offset_db: w.sim.rover_cn0_offset_db } })
      set({ started: true })
    } catch (e) { setErr(e.message) }
  }
  const stop = () => api('/api/gps/sessions/current/stop', { method: 'POST' }).catch(() => {})

  return (
    <>
      {!running && real && (
        <div className="fields">
          <label>Duración (s) — recomendado ≥ 3600
            <input type="number" min="10" value={w.duration_s} onChange={(e) => set({ duration_s: Number(e.target.value) })} />
          </label>
        </div>
      )}
      {!running && <p className="muted note">Las antenas no deben moverse durante el registro. Cada sesión guarda <code>ref.nmea</code>, <code>rover.nmea</code> y <code>meta.json</code>.</p>}
      <div className="row">
        {running
          ? <button className="btn-primary stop" onClick={stop}>Detener</button>
          : <button className="btn-primary" disabled={!online} onClick={start}>{w.started ? 'Nueva sesión' : 'Iniciar registro'}</button>}
        {status && <span className="muted">Sesión {running ? 'en curso' : 'finalizada'} · {Math.round(status.elapsed_s)} s / {dur} s</span>}
      </div>
      {running && (
        <div className="checks">
          {['ref', 'rover'].map((k) => (
            <Check key={k} state={hist[k].length > 0 ? 'ok' : 'run'} title={`Llegan épocas: ${RX[k].label.toLowerCase()}`}
              detail={`${hist[k].length} épocas · ${status?.receivers?.[k]?.bad_lines ?? 0} líneas con error`} />
          ))}
        </div>
      )}
      {(err || status?.error) && <p className="error">{err || status.error}</p>}
    </>
  )
}

function StepDone({ acq, onNavigate }) {
  const { hist, status } = acq
  const fixes = (k) => hist[k].filter((e) => e.quality > 0).length
  const ok = status?.state === 'finished' && !status.error && fixes('ref') > 0 && fixes('rover') > 0
  return (
    <>
      <div className="checks">
        <Check state={status?.state === 'finished' ? (status.error ? 'fail' : 'ok') : 'run'} title="Sesión cerrada y guardada"
          detail={status ? `ID ${status.id} · data/sessions/${status.id}/${status.error ? ' · ' + status.error : ''}` : ''} />
        {['ref', 'rover'].map((k) => (
          <Check key={k} state={fixes(k) > 0 ? 'ok' : 'fail'} title={`${RX[k].label} con épocas válidas`}
            detail={`${fixes(k)} de ${hist[k].length} con fix`} />
        ))}
      </div>
      <div className="row">
        <button className="btn-primary" disabled={!ok} onClick={() => onNavigate?.('diferencial')}>Ir al análisis diferencial →</button>
      </div>
    </>
  )
}

const INITIAL = {
  mode: null, ports: [], ref: '', rover: '', baud: 9600, nmea: {}, fix: {}, duration_s: 3600, started: false,
  sim: { duration_s: 600, speed: 10, baseline_m: 3, rover_cn0_offset_db: 0, seed: 1 },
}

const STEPS = {
  real: [['mode', 'Origen'], ['be', 'Backend'], ['ports', 'Conectar'], ['nmea', 'Validar NMEA'], ['fix', 'Esperar fix'], ['run', 'Registrar'], ['done', 'Cierre']],
  sim: [['mode', 'Origen'], ['be', 'Backend'], ['sim', 'Escenario'], ['run', 'Registrar'], ['done', 'Cierre']],
}

export default function AcquisitionView({ acq, onNavigate }) {
  const { hist, status, online } = acq
  const running = status?.state === 'running'
  const hasData = hist.ref.length + hist.rover.length > 0
  const [w, setW] = useState(() => ({ ...INITIAL, mode: status?.mode ?? null, started: Boolean(status) }))
  const set = useCallback((patch) => setW((p) => ({ ...p, ...patch })), [])

  const steps = STEPS[w.mode === 'real' ? 'real' : 'sim'].map(([id, label]) => ({ id, label }))
  const last = steps.length - 1
  // Si ya hay una sesión (al volver desde otro módulo) se retoma en Registrar/Cierre.
  const resume = status ? (running ? last - 1 : last) : 0
  const [cur, setCur] = useState(resume)
  const [reached, setReached] = useState(resume)
  const step = steps[Math.min(cur, last)]

  // Al terminar la sesión el asistente avanza solo a Cierre.
  const prevRunning = useRef(running)
  useEffect(() => {
    if (prevRunning.current && !running && hasData) { setCur(last); setReached(last) }
    prevRunning.current = running
  }, [running, hasData, last])

  const passed = {
    mode: Boolean(w.mode),
    be: online,
    ports: w.ports.length >= 2,
    nmea: Boolean(w.nmea.ref?.ok && w.nmea.rover?.ok && w.ref !== w.rover),
    fix: true,
    sim: w.sim.duration_s >= 10 && w.sim.baseline_m > 0,
  }[step.id]

  const go = (i) => { setCur(i); setReached((r) => Math.max(r, i)) }
  const body = {
    mode: <StepMode w={w} set={set} />,
    be: <StepBackend online={online} />,
    ports: <StepPorts w={w} set={set} />,
    nmea: <StepNmea w={w} set={set} />,
    fix: <StepFix w={w} set={set} />,
    sim: <StepSim w={w} set={set} />,
    run: <StepRun w={w} set={set} acq={acq} online={online} />,
    done: <StepDone acq={acq} onNavigate={onNavigate} />,
  }[step.id]

  return (
    <>
      <section className="card wizard">
        <Stepper steps={steps} current={cur} maxReached={reached} onGo={(i) => !running && go(i)} />
        <h2 className="step-title">{cur + 1}. {step.label}</h2>
        {body}
        <div className="wiz-nav">
          <button className="btn-sec" disabled={cur === 0 || running} onClick={() => go(cur - 1)}>← Anterior</button>
          {step.id !== 'done' && step.id !== 'run' && (
            <button className="btn-primary" disabled={!passed} onClick={() => go(cur + 1)}>Siguiente →</button>
          )}
        </div>
      </section>
      {(step.id === 'run' || step.id === 'done') && hasData && (<><Kpis hist={hist} /><Charts hist={hist} /></>)}
    </>
  )
}
