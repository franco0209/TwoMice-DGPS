import { useState } from 'react'
import Check from '../components/Check.jsx'
import { RX } from './AcquisitionLive.jsx'

/* Vista guiada: el asistente da órdenes concretas, una a la vez. La persona las ejecuta
   en el mundo físico y pulsa «Ya lo hice». Lo que el software puede medir (drivers, ping,
   señal) se valida solo; lo que no (mover una antena) se confirma a mano.
   Funciona igual en simulación: se practica el procedimiento sin hardware. */

const kind = (w, k) => w.dev[k].kind
const port = (w, k) => {
  const d = w.dev[k]
  if (w.mode === 'real') return 'al receptor Mighty Mouse'
  if (d.kind === 'usrp-eth') return `al USRP (${d.addr}), puerto RX2`
  if (d.kind === 'usrp-usb') return 'al USRP USB, puerto RX2'
  if (d.kind === 'rtlsdr') return 'al conector SMA del RTL-SDR'
  return 'al receptor'
}
const bl = (w) => w.sim.baseline_m

/** Órdenes por paso y modo. `gate:false` = informativa (no bloquea «Siguiente»). */
export function ordersFor(id, w) {
  const m = w.mode
  switch (id) {
    case 'site':
      return [
        { text: 'Sal a un lugar con cielo abierto (patio, azotea o campo).',
          why: 'La señal GPS es muy débil. Edificios, árboles y paredes la bloquean y la reflejan (multitrayecto), y ese error es justo el que el diferencial NO cancela.' },
        { text: 'Elige un punto A y márcalo en el suelo con cinta o una tiza: ahí irá la REFERENCIA.',
          why: 'La referencia debe quedar fija durante toda la medición. Mientras más conocida su posición, mejor.' },
        { text: `Con una cinta métrica, mide ${bl(w)} m hacia el ESTE desde A y marca el punto B: ahí irá el MÓVIL.`,
          why: 'Esa distancia es la línea base. Con ella el análisis comprueba que el diferencial recupera la posición relativa correcta.' },
        { text: 'Revisa que en 5 m a la redonda de A y B no haya paredes metálicas, vehículos ni árboles altos.',
          why: 'Las superficies metálicas cercanas son la mayor fuente de multitrayecto.' },
      ]
    case 'mount':
      return [
        { text: 'Pon la antena de REFERENCIA sobre el punto A, con la cara plana hacia el cielo, sobre una superficie estable.',
          why: 'Una antena inclinada o en el suelo húmedo pierde satélites bajos. Si es posible, sobre un plano metálico pequeño (plano de tierra) de unos 10 cm.' },
        { text: 'Pon la antena del MÓVIL sobre el punto B, en el mismo sentido y a la misma altura que la otra.',
          why: 'Si las alturas difieren, el análisis vertical mezcla la diferencia de altura con el error.' },
        { text: `Conecta el cable de la antena de referencia ${port(w, 'ref')}.`,
          why: m === 'sdr' ? 'Aún sin alimentación DC: eso se hace en un paso posterior con cuidado.' : 'Solo el cable; todavía no enciendas nada.' },
        { text: `Conecta el cable de la antena del móvil ${port(w, 'rover')}.`,
          why: 'Verifica que cada cable queda en su receptor: el cruce ref/móvil invalida la sesión.' },
        { text: 'Pega una etiqueta «REF» en la antena y el receptor de referencia, y «MÓVIL» en los del móvil.',
          why: 'Es la causa más común de resultados raros: intercambiar sin querer ref y móvil.' },
      ]
    case 'power':
      return [{ text: 'Enciende el receptor de REFERENCIA (en la simulación: pulsa «Ya lo hice» como si lo hicieras).',
          why: 'En el hardware real se encienden antes de comprobar nada. Aquí practicas el orden.' },
        { text: 'Enciende el receptor del MÓVIL.', why: 'Los dos deben estar encendidos para registrar a la vez.' }]
    case 'ports':
      return [
        { text: 'Conecta el receptor de REFERENCIA a la PC (USB o adaptador serie) y aliméntalo.', why: 'Debe aparecer un puerto nuevo en cuanto lo conectas.' },
        { text: 'Conecta el receptor del MÓVIL a la PC y aliméntalo.', why: 'Cada receptor ocupa su propio puerto.' },
      ]
    case 'dev':
      return [
        { text: kind(w, 'ref') === 'usrp-eth' ? `Conecta el cable Ethernet del USRP de REFERENCIA (${w.dev.ref.addr}) al switch o a la PC.`
            : kind(w, 'ref') === 'file' ? 'Ten a mano el archivo IQ de la referencia.' : 'Conecta por USB el receptor de REFERENCIA (USB 3.0 si es un USRP B2xx).',
          why: 'Para Ethernet, la PC debe tener una IP en la misma subred (p. ej. 192.168.10.1/24).' },
        { text: kind(w, 'rover') === 'usrp-eth' ? `Conecta el cable Ethernet del USRP del MÓVIL (${w.dev.rover.addr}) al switch o a la PC.`
            : kind(w, 'rover') === 'file' ? 'Ten a mano el archivo IQ del móvil.' : 'Conecta por USB el receptor del MÓVIL.',
          why: 'Dos USRP con un solo puerto necesitan un switch y cada uno con su propia IP.' },
        { text: 'Enciende los receptores y espera unos 30 segundos hasta que sus luces se estabilicen.',
          why: 'Un USRP tarda en arrancar y cargar su firmware; probar antes da falsos errores.' },
      ]
    case 'ant':
      return [
        { text: 'Si tu antena es ACTIVA (tiene LNA), aliméntala con 3–5 V: bias-tee del RTL-SDR (botón de abajo) o un bias-tee externo para el USRP.',
          why: 'Sin alimentación el LNA no amplifica y no verás señal GPS. El puerto RX2 del USRP no entrega DC por sí mismo.' },
        { text: 'Comprueba que nunca va tensión continua a un puerto sin bloqueo de DC (un bias-tee externo debe ir entre el cable y el puerto).',
          why: 'Es la forma de dañar un USRP. Solo se recibe: este asistente jamás transmite.' },
        { text: 'Confirma que las dos antenas siguen en su sitio, a cielo abierto y sin nada encima.', why: 'Se acaba de manipular cableado: es fácil mover una antena.' },
      ]
    case 'cap':
      return [{ text: 'Aléjate de las antenas y no las toques durante la captura (2 s).',
          why: 'Tocar o acercarse a una antena activa cambia su ganancia y distorsiona la medida del nivel.' }]
    case 'gnss':
      return [{ text: 'Aléjate del equipo y no muevas ni tapes las antenas mientras buscan satélites.',
          why: 'En el arranque en frío tarda varios minutos: primero adquiere, luego rastrea, luego decodifica la navegación y recién entonces da posición.' }]
    case 'fix':
      return [{ text: 'Espera sin tocar nada hasta ver «fix obtenido» en los dos receptores (puede tardar un minuto o más).',
          why: 'Moverse durante el arranque en frío lo retrasa.', gate: false }]
    case 'run':
      return [
        { text: `Comprueba por última vez que las antenas están fijas: REF en A y MÓVIL en B, a ${bl(w)} m.`, why: 'No se pueden mover durante todo el registro: movería la «verdad» del experimento.' },
        { text: 'Apunta en tu cuaderno la hora de inicio, el clima y cualquier obstáculo cercano.', why: 'Sirve después para explicar resultados raros en el informe.' },
      ]
    case 'done':
      return [
        { text: 'Si usaste bias-tee: desconecta primero la alimentación de las antenas activas y luego los cables.', why: 'Desconectar con tensión puede dañar el LNA o el puerto.', gate: false },
        { text: 'Recoge antenas y receptores, y guarda la hora de fin y las observaciones.', why: 'Completa tu bitácora del experimento.', gate: false },
      ]
    default:
      return null
  }
}

export const ordersKey = (id, i) => `${id}:${i}`
export const ordersDone = (w, id) => (ordersFor(id, w) ?? []).every((o, i) => o.gate === false || w.done[ordersKey(id, i)])

/** Lista de órdenes: solo la primera pendiente está activa; el resto espera. */
export function Orders({ id, w, set }) {
  const items = ordersFor(id, w)
  const [open, setOpen] = useState(null)
  if (!items) return null
  const done = items.map((_, i) => Boolean(w.done[ordersKey(id, i)]))
  const cur = done.findIndex((d) => !d)
  const n = done.filter(Boolean).length
  const toggle = (i) => set({ done: { ...w.done, [ordersKey(id, i)]: !done[i] } })
  return (
    <section className={`coach ${cur === -1 ? 'all' : ''}`} aria-label="Órdenes de este paso">
      <header>
        <span className="coach-badge">{cur === -1 ? '✓ Todo listo' : 'Haz esto ahora'}</span>
        <span className="coach-count">{n} de {items.length}</span>
        <i className="coach-bar"><b style={{ width: `${(n / items.length) * 100}%` }} /></i>
      </header>
      <ol>
        {items.map((o, i) => {
          const state = done[i] ? 'done' : i === cur ? 'cur' : 'lock'
          return (
            <li key={ordersKey(id, i)} className={state}>
              <span className="o-num">{done[i] ? '✓' : i + 1}</span>
              <div className="o-body">
                <p>{o.text}{o.gate === false && <em> (opcional)</em>}</p>
                {o.why && (state !== 'lock') && (
                  <>
                    <button type="button" className="o-why-btn" onClick={() => setOpen(open === ordersKey(id, i) ? null : ordersKey(id, i))}>¿Por qué?</button>
                    {(open === ordersKey(id, i) || state === 'cur') && <small className="o-why">{o.why}</small>}
                  </>
                )}
              </div>
              {state === 'cur' && <button type="button" className="btn-primary o-btn" onClick={() => toggle(i)}>Ya lo hice</button>}
              {state === 'done' && <button type="button" className="o-undo" onClick={() => toggle(i)}>deshacer</button>}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

/** Diagrama animado del montaje: A (referencia), B (móvil), línea base y norte. */
export function SiteDiagram({ baseline }) {
  return (
    <figure className="site-diagram">
      <svg viewBox="0 0 520 190" role="img" aria-label={`Referencia en A y móvil en B separados ${baseline} metros hacia el este`}>
        <defs>
          <linearGradient id="gsky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity=".22" /><stop offset="1" stopColor="var(--accent)" stopOpacity="0" /></linearGradient>
          <marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L8 4L0 8z" fill="var(--muted)" /></marker>
        </defs>
        <rect x="0" y="0" width="520" height="120" fill="url(#gsky)" rx="12" />
        <line x1="20" y1="150" x2="500" y2="150" stroke="var(--line-2)" strokeWidth="2" strokeDasharray="4 6" />
        {[['ref', 110, 'A'], ['rover', 410, 'B']].map(([k, x, n]) => (
          <g key={k} transform={`translate(${x} 0)`}>
            {[0, 1, 2].map((r) => <circle key={r} className="wave" style={{ animationDelay: `${r * 0.7}s` }} cx="0" cy="100" r="14" fill="none" stroke={RX[k].color} strokeWidth="2" />)}
            <rect x="-14" y="98" width="28" height="9" rx="3" fill={RX[k].color} />
            <line x1="0" y1="107" x2="0" y2="150" stroke={RX[k].color} strokeWidth="2" />
            <circle cx="0" cy="150" r="5" fill="var(--card)" stroke={RX[k].color} strokeWidth="3" />
            <text x="0" y="176" textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--text)">{n} · {RX[k].label}</text>
          </g>
        ))}
        <line x1="130" y1="135" x2="390" y2="135" stroke="var(--muted)" strokeWidth="1.5" markerStart="url(#arr)" markerEnd="url(#arr)" />
        <text x="260" y="128" textAnchor="middle" fontSize="13" fontWeight="600" fill="var(--text)">{baseline} m (línea base)</text>
        <g transform="translate(480 30)" fontSize="11" fill="var(--muted)" textAnchor="middle"><path d="M0 22V0M-5 6L0 0l5 6" stroke="var(--muted)" strokeWidth="1.5" fill="none" /><text y="38">N</text></g>
        <text x="470" y="150" fontSize="11" fill="var(--muted)" textAnchor="end" transform="translate(0 -10)">E →</text>
      </svg>
    </figure>
  )
}

export function StepSite({ w, set }) {
  const v = w.sim.baseline_m
  return (
    <>
      {w.mode === 'sim' && <p className="sim-note"><b>Modo simulación:</b> no necesitas hardware, pero haz el procedimiento como si fuera real. Cada orden la confirmas con «Ya lo hice».</p>}
      <div className="fields">
        <label>Línea base entre ref y móvil (m)
          <input type="number" min="0.5" step="0.5" value={v} onChange={(e) => set({ sim: { ...w.sim, baseline_m: Number(e.target.value) }, done: { ...w.done, [ordersKey('site', 2)]: false } })} />
        </label>
      </div>
      <SiteDiagram baseline={v} />
    </>
  )
}

export function StepMount({ w }) {
  return (
    <>
      <SiteDiagram baseline={w.sim.baseline_m} />
      <p className="muted note">Antenas activas: las dos deben ser iguales y estar a la misma altura.</p>
    </>
  )
}

/** Solo simulación: los «receptores» se encienden y se comprueban solos tras la orden. */
export function StepPower({ w, set }) {
  const [busy, setBusy] = useState(false)
  const run = () => {
    setBusy(true)
    setTimeout(() => { set({ simHw: { ref: true } }) }, 900)
    setTimeout(() => { set({ simHw: { ref: true, rover: true } }); setBusy(false) }, 1900)
  }
  const hw = w.simHw ?? {}
  return (
    <>
      <p>Cuando hayas hecho lo anterior, comprueba que el programa «ve» a los receptores (aquí simulados).</p>
      <div className="checks">
        {['ref', 'rover'].map((k) => (
          <Check key={k} state={hw[k] ? 'ok' : busy ? 'run' : 'idle'} title={`${RX[k].label}: ${hw[k] ? 'receptor simulado listo' : 'pendiente'}`}
            detail={hw[k] ? 'Simulado: en el hardware real aquí se ejecutaría el ping / detección.' : 'Sin comprobar.'} />
        ))}
      </div>
      <div className="row"><button className="btn-sec" disabled={busy || !ordersDone(w, 'power')} onClick={run}>{busy ? 'Comprobando…' : 'Comprobar receptores'}</button>
        {!ordersDone(w, 'power') && <span className="muted note">Primero confirma las órdenes de arriba.</span>}</div>
    </>
  )
}
