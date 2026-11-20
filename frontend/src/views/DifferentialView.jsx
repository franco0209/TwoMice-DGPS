import { useEffect, useState } from 'react'
import DgpsResult from '../components/DgpsResult.jsx'

async function api(path, opts) {
  const r = await fetch(path, opts)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `Error ${r.status}`)
  return j
}

const EMPTY = { lat: '', lon: '', h: '' }
const pos = (p) => (p.lat !== '' && p.lon !== '' && p.h !== '' ? { lat: +p.lat, lon: +p.lon, h: +p.h } : null)

function PosFields({ title, value, set }) {
  return (
    <>
      {[['lat', 'Latitud (°)'], ['lon', 'Longitud (°)'], ['h', 'Altura elipsoidal (m)']].map(([k, l]) => (
        <label key={k}>{title} · {l}
          <input type="number" step="any" value={value[k]} onChange={(e) => set({ ...value, [k]: e.target.value })} />
        </label>
      ))}
    </>
  )
}

export default function DifferentialView({ result, setResult }) {
  const [src, setSrc] = useState('session') // session | upload
  const [sessions, setSessions] = useState([])
  const [sid, setSid] = useState('')
  const [ref, setRef] = useState(EMPTY)
  const [rov, setRov] = useState(EMPTY)
  const [files, setFiles] = useState({ ref: null, rover: null })
  const [nboot, setNboot] = useState(500)
  const [block, setBlock] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api('/api/analysis/experiments').then((l) => {
      setSessions(l)
      setSid((s) => s || l.find((x) => x.epochs)?.id || '')
    }).catch((e) => setErr(e.message))
  }, [])

  const cur = sessions.find((s) => s.id === sid)

  async function run() {
    setBusy(true)
    setErr('')
    try {
      let res
      if (src === 'session') {
        res = await api('/api/analysis/run', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid, ref_known: pos(ref), rover_truth: pos(rov), n_boot: nboot, block: block ? +block : null }),
        })
      } else {
        const p = pos(ref)
        if (!p || !files.ref || !files.rover) throw new Error('Suba ambos .nmea e indique la posición conocida de la referencia')
        const fd = new FormData()
        fd.append('ref_file', files.ref)
        fd.append('rover_file', files.rover)
        fd.append('ref_lat', p.lat)
        fd.append('ref_lon', p.lon)
        fd.append('ref_h', p.h)
        const q = pos(rov)
        if (q) {
          fd.append('rover_lat', q.lat)
          fd.append('rover_lon', q.lon)
          fd.append('rover_h', q.h)
        }
        fd.append('n_boot', nboot)
        if (block) fd.append('block', block)
        res = await api('/api/analysis/upload', { method: 'POST', body: fd })
      }
      setResult(res)
    } catch (e) {
      setErr(e instanceof TypeError ? 'No se pudo contactar al backend (¿uvicorn en :8000?)' : e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <section className="card">
        <div className="ctrl-head">
          <div className="seg">
            {[['session', 'Sesión guardada'], ['upload', 'Subir logs .nmea']].map(([k, l]) => (
              <button key={k} className={src === k ? 'on' : ''} onClick={() => setSrc(k)}>{l}</button>
            ))}
          </div>
          <div className="ctrl-actions">
            <button className="btn-primary" disabled={busy || (src === 'session' && !sid)} onClick={run}>
              {busy ? 'Calculando…' : 'Calcular diferencial'}
            </button>
          </div>
        </div>
        <div className="fields">
          {src === 'session' ? (
            <label>Sesión
              <select value={sid} onChange={(e) => setSid(e.target.value)}>
                <option value="">— elegir —</option>
                {sessions.filter((s) => s.epochs).map((s) => (
                  <option key={s.id} value={s.id}>{s.id} · {s.mode}{s.summary ? ' · analizada' : ''}</option>
                ))}
              </select>
            </label>
          ) : (
            ['ref', 'rover'].map((k) => (
              <label key={k}>Log {k === 'ref' ? 'referencia' : 'móvil'} (.nmea)
                <input type="file" accept=".nmea,.txt,.log" onChange={(e) => setFiles({ ...files, [k]: e.target.files[0] })} />
              </label>
            ))
          )}
          <label>Remuestreos bootstrap<input type="number" min="0" max="5000" value={nboot} onChange={(e) => setNboot(+e.target.value)} /></label>
          <label>Bloque (épocas, vacío = auto)<input type="number" min="1" value={block} onChange={(e) => setBlock(e.target.value)} /></label>
        </div>
        <div className="fields">
          <PosFields title="Ref. conocida" value={ref} set={setRef} />
          <PosFields title="Móvil verdadero (opc.)" value={rov} set={setRov} />
        </div>
        <p className="muted note">
          {src === 'session' && cur?.has_truth
            ? 'Sesión simulada: si deja las posiciones vacías se usa la verdad exacta de la simulación.'
            : 'Datos reales: la posición conocida de la referencia es obligatoria y su incertidumbre limita el resultado (altura elipsoidal, no sobre el geoide). La posición del móvil es opcional: sin ella solo se mide precisión.'}
          {' '}La corrección se aplica solo en épocas donde ambos receptores usaron el mismo conjunto de satélites.
        </p>
        {err && <p className="error">{err}</p>}
      </section>
      {result ? <DgpsResult r={result} /> : (
        <section className="card empty"><p className="muted">Elija una sesión (o suba dos logs) y calcule el diferencial.</p></section>
      )}
    </>
  )
}
