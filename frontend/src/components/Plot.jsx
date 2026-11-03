import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const PlotlyChart = createPlotlyComponent(Plotly)

const dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
const fg = dark ? '#e6e9ef' : '#1c2330'
const grid = dark ? '#2a3242' : '#e2e5ea'

export default function Plot({ data, layout, height = 340 }) {
  return (
    <PlotlyChart
      data={data}
      layout={{
        height,
        margin: { l: 55, r: 15, t: 20, b: 45 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: fg, size: 12 },
        legend: { orientation: 'h', y: -0.2 },
        ...layout,
        xaxis: { gridcolor: grid, zerolinecolor: grid, ...layout?.xaxis },
        yaxis: { gridcolor: grid, zerolinecolor: grid, ...layout?.yaxis },
      }}
      config={{ displaylogo: false, responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  )
}
