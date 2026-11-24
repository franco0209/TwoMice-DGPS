import { useCallback, useEffect, useState } from 'react'
import Check from '../components/Check.jsx'
import Plot from '../components/Plot.jsx'
import { api, fmt, RX } from './AcquisitionLive.jsx'
import { ordersDone } from './Guide.jsx'

/* Pasos del asistente para adquisición con SDR (USRP / RTL-SDR) + GNSS-SDR.
   Solo recepción. Cada paso valida contra /api/sdr/* y bloquea «Siguiente» hasta pasar. */

const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const RXS = ['ref', 'rover']

export const KINDS = {
  'usrp-eth': { label: 'USRP · Ethernet', hint: 'X3xx/N2xx por 1/10 GbE. Requiere IP en la subred del equipo.' },
  'usrp-usb': { label: 'USRP · USB', hint: 'B200/B210/B205mini por USB 3.0.' },
  rtlsdr: { label: 'RTL-SDR', hint: 'Dongle USB; un canal por dongle (ref y móvil = dos dongles).' },
  file: { label: 'Archivo IQ', hint: 'Captura grabada (sc16 / uint8). Útil para validar sin hardware.' },
}

const defaultDev = (kind = 'usrp-eth') => ({ kind, addr: '192.168.10.2', serial: '', index: 0, fs: 2.0, gain: 40, file: '', sample: 'ishort', subdevice: '', antenna: 'RX2' })

export const SDR_INITIAL = {
  dev: { ref: defaultDev(), rover: { ...defaultDev(), addr: '192.168.10.3' } },
  sdr: { tools: null, ping: {}, usb: null, find: {}, probe: {}, cap: {}, ack: false, saveIq: false, biast: {} },
  sdrDuration: 3600,
  done: {}, simHw: {},
}

export const SDR_STEPS = [['mode', 'Origen'], ['be', 'Backend'], ['tools', 'Herramientas'], ['site', 'Lugar'], ['mount', 'Montaje'], ['dev', 'Conectar'], ['find', 'Detectar'],
  ['probe', 'Sondear'], ['ant', 'Antena'], ['cap', 'Captura'], ['gnss', 'GNSS-SDR'], ['run', 'Registrar'], ['done', 'Cierre']]

/** Convierte la config de la UI a lo que entiende la API. */
const apiKind = (d) => (d.kind === 'rtlsdr' ? 'rtlsdr' : 'usrp')
const apiArgs = (d) => (d.kind === 'usrp-eth' ? `addr=${d.addr}` : d.kind === 'usrp-usb' && d.serial ? `serial=${d.serial}` : '')
const needsHw = (d) => d.kind !== 'file'

const sdrSet = (w, set) => (patch) => set({ sdr: { ...w.sdr, ...patch } })
/** Aplica `patch` a un campo por receptor ({ref, rover}) de w.sdr, sin pisar el otro. */
const putRx = (w, set, field, k, v) => set({ sdr: { ...w.sdr, [field]: { ...w.sdr[field], [k]: v } } })

function RxCheck({ k, r, busy, okText, idleText = 'Sin probar.' }) {
  return (
    <Check state={busy ? 'run' : !r ? 'idle' : r.ok ? 'ok' : 'fail'} title={`${RX[k].label}: ${r?.ok ? okText(r) : r ? 'falló' : 'pendiente'}`}
      detail={!r ? idleText : r.message} />
  )
}

/** Ejecuta `fn(k)` para cada receptor en paralelo y guarda el resultado en w.sdr[field]. */
function useEachRx(w, set, field, fn) {
  const [busy, setBusy] = useState(false)
  const run = useCallback(async () => {
    setBusy(true)
    const res = {}
    await Promise.all(RXS.map(async (k) => {
      if (!needsHw(w.dev[k])) { res[k] = { ok: true, message: 'Archivo IQ: no requiere hardware.' }; return }
      try { res[k] = await fn(k, w.dev[k]) } catch (e) { res[k] = { ok: false, message: e.message } }
    }))
    set({ sdr: { ...w.sdr, [field]: res } })
    setBusy(false)
  }, [w, set, field, fn])
  return [busy, run]
}

function StepTools({ w, set }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const s = sdrSet(w, set)
  const scan = useCallback(async () => {
    setBusy(true); setErr('')
    try { s({ tools: await api('/api/sdr/tools') }) } catch (e) { setErr(e.message) }
    setBusy(false)
  }, [w.sdr]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!w.sdr.tools) scan() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const t = w.sdr.tools
  return (
    <>
      <p>Compruebe que están instaladas las herramientas del sistema. Se usan en cada etapa: <code>uhd_find_devices</code>, <code>uhd_usrp_probe</code>, <code>rtl_test</code> y <code>gnss-sdr</code>.</p>
      {err && <p className="error">{err}</p>}
      <div className="checks">
        {t && Object.entries(t.tools).map(([name, v]) => (
          <Check key={name} state={v.installed ? 'ok' : name === 'rtl_biast' ? 'idle' : 'fail'} title={name}
            detail={v.installed ? `${v.path}${v.version ? ' · ' + v.version : ''}` : name === 'rtl_biast' ? 'Opcional (bias-tee del RTL-SDR).' : 'No instalado'} />
        ))}
        {t?.hints.map((h) => <p key={h} className="muted note">{h}</p>)}
      </div>
      <div className="row"><button className="btn-sec" disabled={busy} onClick={scan}>{busy ? 'Comprobando…' : 'Volver a comprobar'}</button></div>
    </>
  )
}

function DevFields({ k, w, set }) {
  const d = w.dev[k]
  const upd = (patch) => set({ dev: { ...w.dev, [k]: { ...d, ...patch } }, sdr: { ...w.sdr, ping: {}, find: {}, probe: {}, cap: {} } })
  const num = (f, extra = {}) => ({ type: 'number', value: d[f], ...extra, onChange: (e) => upd({ [f]: Number(e.target.value) }) })
  return (
    <fieldset className="card-sub">
      <legend>{RX[k].label}</legend>
      <div className="fields">
        <label>Tipo de receptor
          <select value={d.kind} onChange={(e) => upd({ kind: e.target.value })}>
            {Object.entries(KINDS).map(([id, v]) => <option key={id} value={id}>{v.label}</option>)}
          </select>
        </label>
        {d.kind === 'usrp-eth' && <label>IP del USRP<input value={d.addr} onChange={(e) => upd({ addr: e.target.value })} /></label>}
        {d.kind === 'usrp-usb' && <label>Serial (opcional)<input value={d.serial} onChange={(e) => upd({ serial: e.target.value })} /></label>}
        {d.kind === 'rtlsdr' && <label>Índice del dongle<input {...num('index', { min: 0, max: 16 })} /></label>}
        {d.kind === 'file' && <label>Ruta del archivo IQ<input value={d.file} placeholder="/ruta/captura.iq" onChange={(e) => upd({ file: e.target.value })} /></label>}
        {d.kind === 'file' && (
          <label>Formato
            <select value={d.sample} onChange={(e) => upd({ sample: e.target.value })}>
              <option value="ishort">sc16 (USRP)</option><option value="byte">uint8 (RTL-SDR)</option><option value="gr_complex">float complejo</option>
            </select>
          </label>
        )}
        {needsHw(d) && <label>Sample rate (MS/s)<input {...num('fs', { min: 0.5, max: 10, step: 0.256 })} /></label>}
        {needsHw(d) && <label>Ganancia (dB)<input {...num('gain', { min: 0, max: 76, step: 1 })} /></label>}
      </div>
      <p className="muted note">{KINDS[d.kind].hint}</p>
    </fieldset>
  )
}

function StepDevices({ w, set }) {
  const [busy, run] = useEachRx(w, set, 'ping', (k, d) => (d.kind === 'usrp-eth'
    ? post('/api/sdr/ping', { ip: d.addr, count: 3 })
    : api('/api/sdr/usb').then((u) => {
        const want = d.kind === 'rtlsdr' ? 'rtlsdr' : 'usrp'
        const n = u.devices.filter((x) => x.kind === want).length
        return { ok: n > 0, message: n > 0 ? `${n} ${want === 'rtlsdr' ? 'RTL-SDR' : 'USRP'} en el bus USB` : u.message }
      })))
  const same = RXS.every((k) => w.dev[k].kind === 'usrp-eth') && w.dev.ref.addr === w.dev.rover.addr
  const sameIdx = RXS.every((k) => w.dev[k].kind === 'rtlsdr') && w.dev.ref.index === w.dev.rover.index
  return (
    <>
      <p>Elija el tipo de cada receptor y pulse «Comprobar conexión» (ping para Ethernet; <code>lsusb</code> para USB).</p>
      {RXS.map((k) => <DevFields key={k} k={k} w={w} set={set} />)}
      {same && <p className="error">Ref y móvil no pueden usar la misma IP. Con un solo USRP de 2 canales use el mismo equipo con subdevice distinto (A:A / A:B).</p>}
      {sameIdx && <p className="error">Ref y móvil no pueden usar el mismo dongle RTL-SDR: se necesitan dos.</p>}
      <div className="checks">
        {RXS.map((k) => <RxCheck key={k} k={k} r={w.sdr.ping[k]} busy={busy} okText={() => 'conectado'} />)}
      </div>
      <div className="row"><button className="btn-sec" disabled={busy || same || sameIdx} onClick={run}>{busy ? 'Comprobando…' : 'Comprobar conexión'}</button></div>
    </>
  )
}

function StepFind({ w, set }) {
  const [busy, run] = useEachRx(w, set, 'find', (k, d) => post('/api/sdr/find', { kind: apiKind(d), args: apiArgs(d), index: d.index }).then((r) => ({
    ...r, message: r.ok && r.devices?.[0]?.serial ? `${r.message} · serial ${r.devices[0].serial}` : r.message })))
  return (
    <>
      <p>UHD debe «ver» cada USRP (<code>uhd_find_devices</code>); para RTL-SDR se ejecuta <code>rtl_test -t</code>.</p>
      <div className="checks">{RXS.map((k) => <RxCheck key={k} k={k} r={w.sdr.find[k]} busy={busy} okText={() => 'detectado'} />)}</div>
      <div className="row"><button className="btn-sec" disabled={busy} onClick={run}>{busy ? 'Buscando…' : 'Detectar'}</button></div>
    </>
  )
}

function StepProbe({ w, set }) {
  const [busy, run] = useEachRx(w, set, 'probe', (k, d) => post('/api/sdr/probe', { kind: apiKind(d), args: apiArgs(d), index: d.index }))
  return (
    <>
      <p>Sondeo completo: modelo, canales RX y rango de ganancia/frecuencia (debe cubrir 1575.42 MHz). Puede tardar hasta un minuto la primera vez (carga de FPGA).</p>
      <div className="checks">
        {RXS.map((k) => {
          const r = w.sdr.probe[k]
          return (
            <Check key={k} state={busy ? 'run' : !r ? 'idle' : r.ok ? 'ok' : 'fail'} title={`${RX[k].label}: ${r?.ok ? (r.product || r.tuner || 'OK') : r ? 'falló' : 'pendiente'}`}
              detail={!r ? 'Sin probar.' : r.ok && r.gain_db ? `${r.rx_channels} canal(es) RX · ganancia ${r.gain_db[0]}–${r.gain_db[1]} dB` : r.message} />
          )
        })}
      </div>
      <div className="row"><button className="btn-sec" disabled={busy} onClick={run}>{busy ? 'Sondeando…' : 'Sondear'}</button></div>
    </>
  )
}

function StepAntenna({ w, set }) {
  const rtl = RXS.filter((k) => w.dev[k].kind === 'rtlsdr')
  const bias = async (k, on) => {
    try { putRx(w, set, 'biast', k, await post('/api/sdr/biast', { index: w.dev[k].index, on })) } catch (e) { putRx(w, set, 'biast', k, { ok: false, message: e.message }) }
  }
  return (
    <>
      <p>La antena activa (LNA) necesita <b>3–5 V</b> por el coaxial. Esto no se puede medir desde el software: sigue las órdenes.</p>
      {rtl.map((k) => (
        <div className="row" key={k}>
          <span>{RX[k].label} (dongle {w.dev[k].index}):</span>
          <button className="btn-sec" onClick={() => bias(k, true)}>Activar bias-tee</button>
          <button className="btn-sec" onClick={() => bias(k, false)}>Desactivar</button>
          {w.sdr.biast[k] && <span className={w.sdr.biast[k].ok ? 'muted' : 'error'}>{w.sdr.biast[k].message}</span>}
        </div>
      ))}
    </>
  )
}

function Spectrum({ k, r }) {
  if (!r?.spectrum) return null
  const f = r.spectrum.f_hz.map((x) => x / 1e6)
  return (
    <Plot height={240} data={[{ x: f, y: r.spectrum.db, type: 'scatter', mode: 'lines', line: { color: RX[k].color, width: 1 }, name: RX[k].label }]}
      layout={{ title: { text: `${RX[k].label}: espectro (centro 1575.42 MHz)`, font: { size: 13 } }, xaxis: { title: { text: 'Δf (MHz)' } }, yaxis: { title: { text: 'dB/Hz' } }, showlegend: false }} />
  )
}

function StepCapture({ w, set }) {
  const [busy, run] = useEachRx(w, set, 'cap', (k, d) => post('/api/sdr/capture-check', {
    kind: apiKind(d), args: apiArgs(d), index: d.index, fs: d.fs * 1e6, gain: d.gain, seconds: 2,
    ...(w.sdr.saveIq ? { save_as: `${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}-${k}` } : {}) }))
  return (
    <>
      <p>Captura de ~2 s a 1575.42 MHz con la antena a cielo abierto. Se mide nivel, saturación, DC y espectro. Satura → baje la ganancia; nivel muy bajo → revise antena y bias-tee.</p>
      <label className="inline"><input type="checkbox" checked={w.sdr.saveIq} onChange={(e) => set({ sdr: { ...w.sdr, saveIq: e.target.checked } })} /> Guardar el IQ en data/raw/</label>
      <div className="checks">
        {RXS.map((k) => {
          const r = w.sdr.cap[k]
          return (
            <Check key={k} state={busy ? 'run' : !r ? 'idle' : r.ok ? 'ok' : 'fail'} title={`${RX[k].label}: ${r?.ok ? 'señal correcta' : r ? 'revisar' : 'pendiente'}`}
              detail={!r ? 'Sin probar.' : r.power_dbfs != null
                ? `${fmt(r.power_dbfs)} dBFS · saturación ${fmt(r.clip_pct)} % · DC ${fmt(r.dc_offset, 2)} · piso ${fmt(r.noise_floor_db)} dB${r.warnings?.length ? ' · ' + r.warnings.join(' ') : ''}${r.iq_file ? ' · guardado ' + r.iq_file : ''}`
                : r.message} />
          )
        })}
      </div>
      {RXS.map((k) => <Spectrum key={k} k={k} r={w.sdr.cap[k]} />)}
      <div className="row"><button className="btn-sec" disabled={busy} onClick={run}>{busy ? 'Capturando…' : 'Capturar y analizar'}</button></div>
    </>
  )
}

const sdrCfg = (d) => ({
  source: d.kind === 'file' ? 'file' : d.kind === 'rtlsdr' ? 'rtlsdr' : 'usrp',
  device_args: apiArgs(d), rtl_index: d.index, subdevice: d.subdevice, antenna: d.antenna,
  fs: d.fs * 1e6, gain: d.gain, file_path: d.file, sample_type: d.sample })

function StepGnss({ w, set, acq }) {
  const { status } = acq
  const [err, setErr] = useState('')
  const running = status?.state === 'running' && status.mode === 'sdr'
  const start = async () => {
    setErr(''); acq.reset()
    try {
      await post('/api/gps/sessions', { mode: 'sdr', duration_s: w.sdrDuration, sdr_ref: sdrCfg(w.dev.ref), sdr_rover: sdrCfg(w.dev.rover) })
      set({ started: true })
    } catch (e) { setErr(e.message) }
  }
  const stop = () => api('/api/gps/sessions/current/stop', { method: 'POST' }).catch(() => {})
  return (
    <>
      <p>Se lanza un proceso <code>gnss-sdr</code> por receptor. El arranque en frío puede tardar <b>varios minutos</b>: primero adquiere satélites, luego rastrea, decodifica la navegación y recién entonces da el primer fix.</p>
      {!running && (
        <div className="fields">
          <label>Duración (s) — recomendado ≥ 3600
            <input type="number" min="10" value={w.sdrDuration} onChange={(e) => set({ sdrDuration: Number(e.target.value) })} />
          </label>
        </div>
      )}
      <div className="row">
        {running ? <button className="btn-primary stop" onClick={stop}>Detener</button> : <button className="btn-primary" disabled={!acq.online || !ordersDone(w, 'gnss')} onClick={start}>Iniciar GNSS-SDR</button>}
        {status && <span className="muted">{running ? 'en curso' : status.state} · {Math.round(status.elapsed_s)} s</span>}
      </div>
      <div className="checks">
        {RXS.map((k) => {
          const p = status?.sdr?.[k]
          const fix = status?.receivers?.[k]?.last?.quality > 0
          return (
            <Check key={k} state={!p ? 'idle' : fix ? 'ok' : 'run'} title={`${RX[k].label}: ${!p ? 'sin iniciar' : fix ? 'fix obtenido' : p.tracking.length ? 'rastreando…' : 'buscando satélites…'}`}
              detail={p ? `Adquiridos ${p.acquired.length} · rastreados ${p.tracking.length} (PRN ${p.tracking.join(', ') || '—'}) · con navegación ${p.nav_decoded.length} · NMEA ${p.nmea_bytes} B${p.running ? '' : ' · proceso terminado'}` : ''} />
          )
        })}
      </div>
      {running && RXS.map((k) => status.sdr?.[k]?.log_tail?.length > 0 && (
        <details key={k}><summary>Registro de gnss-sdr: {RX[k].label}</summary><pre className="log">{status.sdr[k].log_tail.join('\n')}</pre></details>
      ))}
      {(err || status?.error) && <p className="error">{err || status.error}</p>}
    </>
  )
}

export const SDR_STEP_BODIES = (w, set, acq) => ({
  tools: <StepTools w={w} set={set} />,
  dev: <StepDevices w={w} set={set} />,
  find: <StepFind w={w} set={set} />,
  probe: <StepProbe w={w} set={set} />,
  ant: <StepAntenna w={w} set={set} />,
  cap: <StepCapture w={w} set={set} />,
  gnss: <StepGnss w={w} set={set} acq={acq} />,
})

const all = (w, field) => RXS.every((k) => w.sdr[field][k]?.ok)
/** ¿Se puede avanzar desde este paso? (solo pasos propios del flujo SDR; `undefined` si no aplica). */
export function sdrPassed(id, w, acq) {
  const t = w.sdr.tools
  const kinds = RXS.map((k) => w.dev[k].kind)
  const need = (kind) => (kind === 'rtlsdr' ? 'rtlsdr' : 'usrp')
  switch (id) {
    case 'tools': return Boolean(t?.tools['gnss-sdr'].installed) && kinds.every((k) => k === 'file' || t.ready[need(k)])
    case 'dev': return all(w, 'ping') && !(RXS.every((k) => w.dev[k].kind === 'usrp-eth') && w.dev.ref.addr === w.dev.rover.addr)
    case 'find': return all(w, 'find')
    case 'probe': return all(w, 'probe')
    case 'ant': return true // las órdenes (Guide.jsx) confirman la alimentación
    case 'cap': return all(w, 'cap')
    case 'gnss': return acq.status?.mode === 'sdr' && acq.status.state !== 'idle'
    default: return undefined
  }
}
