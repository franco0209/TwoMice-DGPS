import Plot from './Plot.jsx'

const B = '#f59e0b' // 1 receptor
const A = '#2563eb' // diferencial
const f = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : v.toFixed(d))

const circle = (r, color, name, dash) => {
  const t = Array.from({ length: 121 }, (_, i) => (i * 2 * Math.PI) / 120)
  return {
    x: t.map((a) => r * Math.cos(a)), y: t.map((a) => r * Math.sin(a)), mode: 'lines', name,
    line: { color, width: 1.4, dash }, hoverinfo: 'skip',
  }
}

function hist(vals, max, bins = 30) {
  const w = max / bins
  const c = Array(bins).fill(0)
  for (const v of vals) c[Math.min(bins - 1, Math.floor(v / w))]++
  return { x: c.map((_, i) => (i + 0.5) * w), y: c, w }
}

export default function DgpsResult({ r }) {
  const eb = r.series.before
  const ea = r.series.after
  const rb = eb.map(([e, n]) => Math.hypot(e, n))
  const ra = ea.map(([e, n]) => Math.hypot(e, n))
  const t = r.series.t_s.map((s) => s / 60)
  const ci = r.bootstrap.ci ?? {}
  const rng = (k) => (ci[k] ? `[${f(ci[k][0])}, ${f(ci[k][1])}]` : '—')
  const ep = r.epochs
  const bl = r.baseline
  const max = Math.max(...rb, ...ra, 1e-9)
  const hb = hist(rb, max)
  const ha = hist(ra, max)

  const rows = [
    ['RMSE horizontal (m)', 'rmse_h'], ['CEP50 (m)', 'cep50'], ['CEP95 (m)', 'cep95'], ['2DRMS (m)', '2drms'],
  ]

  return (
    <>
      {!r.accuracy && (
        <p className="warn">
          Sin verdad del móvil: las cifras miden <strong>precisión</strong> (dispersión respecto a la propia media);
          el sesgo común no es observable. Indique la posición real del móvil para medir exactitud.
        </p>
      )}
      <div className="kpis">
        <div className="kpi">
          <span>CEP50: 1 receptor → diferencial</span>
          <strong>{f(r.before.cep50)} → {f(r.after.cep50)} m</strong>
          <small>mejora {f(r.improvement.cep50, 0)} % · IC95 {rng('imp_cep50')} %</small>
        </div>
        <div className="kpi">
          <span>CEP95</span>
          <strong>{f(r.before.cep95)} → {f(r.after.cep95)} m</strong>
          <small>mejora {f(r.improvement.cep95, 0)} % · IC95 {rng('imp_cep95')} %</small>
        </div>
        <div className="kpi">
          <span>2DRMS</span>
          <strong>{f(r.before['2drms'])} → {f(r.after['2drms'])} m</strong>
          <small>mejora {f(r.improvement['2drms'], 0)} %</small>
        </div>
        <div className="kpi">
          <span>Épocas con el mismo conjunto</span>
          <strong>{f(ep.same_sats_pct, 0)} %</strong>
          <small>{ep.same_sats} usadas · {ep.discarded} descartadas de {ep.simultaneous}</small>
        </div>
      </div>

      <div className="grid2">
        <section className="card">
          <h2>Dispersión horizontal con círculos CEP (m)</h2>
          <Plot
            height={420}
            data={[
              { x: eb.map((p) => p[0]), y: eb.map((p) => p[1]), mode: 'markers', name: '1 receptor', marker: { size: 4, color: B, opacity: 0.5 } },
              { x: ea.map((p) => p[0]), y: ea.map((p) => p[1]), mode: 'markers', name: 'Diferencial', marker: { size: 4, color: A, opacity: 0.5 } },
              circle(r.before.cep50, B, 'CEP50 1 rx', 'dash'), circle(r.after.cep50, A, 'CEP50 DGPS', 'dash'),
              circle(r.before.cep95, B, 'CEP95 1 rx'), circle(r.after.cep95, A, 'CEP95 DGPS'),
            ]}
            layout={{ xaxis: { title: { text: 'Este (m)' } }, yaxis: { title: { text: 'Norte (m)' }, scaleanchor: 'x' } }}
          />
        </section>
        <section className="card">
          <h2>Histograma del error horizontal</h2>
          <Plot
            height={420}
            data={[
              { type: 'bar', x: hb.x, y: hb.y, width: hb.w, name: '1 receptor', marker: { color: B }, opacity: 0.65 },
              { type: 'bar', x: ha.x, y: ha.y, width: ha.w, name: 'Diferencial', marker: { color: A }, opacity: 0.65 },
            ]}
            layout={{ barmode: 'overlay', xaxis: { title: { text: 'Error (m)' } }, yaxis: { title: { text: 'Épocas' } } }}
          />
        </section>
        {[['Este', 0], ['Norte', 1], ['Vertical', 2]].map(([l, i]) => (
          <section className="card" key={l}>
            <h2>Error {l} (m)</h2>
            <Plot
              data={[
                { x: t, y: eb.map((p) => p[i]), mode: 'lines', name: '1 receptor', line: { color: B, width: 1 } },
                { x: t, y: ea.map((p) => p[i]), mode: 'lines', name: 'Diferencial', line: { color: A, width: 1 } },
              ]}
              layout={{ xaxis: { title: { text: 'Tiempo (min)' } }, yaxis: { title: { text: 'm' } } }}
            />
          </section>
        ))}
      </div>

      <section className="card">
        <h2>Métricas</h2>
        <table>
          <thead><tr><th>Métrica</th><th>1 receptor</th><th>IC 95 %</th><th>Diferencial</th><th>IC 95 %</th><th>Mejora</th></tr></thead>
          <tbody>
            {rows.map(([l, k]) => (
              <tr key={k}>
                <td>{l}</td><td>{f(r.before[k])}</td><td>{rng(`before_${k}`)}</td>
                <td>{f(r.after[k])}</td><td>{rng(`after_${k}`)}</td><td>{f(r.improvement[k], 0)} %</td>
              </tr>
            ))}
            <tr><td>RMSE vertical (m)</td><td>{f(r.before.rmse_v)}</td><td>—</td><td>{f(r.after.rmse_v)}</td><td>—</td><td>{f(r.improvement.rmse_v, 0)} %</td></tr>
            <tr><td>Sesgo horizontal (m)</td><td>{f(r.before.bias_h)}</td><td>—</td><td>{f(r.after.bias_h)}</td><td>—</td><td>—</td></tr>
            <tr><td>σ Este / Norte (m)</td><td>{f(r.before.std_e)} / {f(r.before.std_n)}</td><td>—</td><td>{f(r.after.std_e)} / {f(r.after.std_n)}</td><td>—</td><td>—</td></tr>
            <tr><td>CEP50 de precisión (m)</td><td>{f(r.before.cep50_prec)}</td><td>—</td><td>{f(r.after.cep50_prec)}</td><td>—</td><td>—</td></tr>
          </tbody>
        </table>
        <p className="muted note">
          IC por bootstrap circular de bloques (bloque = {r.bootstrap.block} épocas, {r.bootstrap.n_boot} remuestreos,
          pareado antes/después). Autocorrelación lag-1 del error: {f(r.stability.lag1_before)} → {f(r.stability.lag1_after)}.
          {' '}Referencia sin filtrar (todas las épocas simultáneas): CEP50 {f(r.raw_all.cep50)} m.
        </p>
      </section>

      <section className="card">
        <h2>Línea base referencia → móvil</h2>
        <table>
          <thead><tr><th></th><th>Longitud (m)</th><th>σ (m)</th>{bl.true_len != null && <th>Error RMS (m)</th>}</tr></thead>
          <tbody>
            <tr><td>1 receptor (móvil − ref conocida)</td><td>{f(bl.raw_len_mean)}</td><td>{f(bl.raw_len_std)}</td>{bl.true_len != null && <td>{f(bl.raw_len_err_rmse)}</td>}</tr>
            <tr><td>Diferencial</td><td>{f(bl.dgps_len_mean)}</td><td>{f(bl.dgps_len_std)}</td>{bl.true_len != null && <td>{f(bl.dgps_len_err_rmse)}</td>}</tr>
            {bl.true_len != null && <tr><td>Verdadera</td><td>{f(bl.true_len)}</td><td>—</td><td>—</td></tr>}
          </tbody>
        </table>
      </section>
    </>
  )
}
