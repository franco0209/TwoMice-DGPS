import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const PlotlyChart = createPlotlyComponent(Plotly)

const isDark = () => {
  const t = document.documentElement.getAttribute('data-theme')
  return t ? t === 'dark' : window.matchMedia?.('(prefers-color-scheme: dark)').matches
}

export default function Plot({ data, layout, height = 340 }) {
  const dark = isDark()
  const fg = dark ? '#e8ecf5' : '#121a2b'
  const grid = dark ? '#1f2940' : '#e3e8f1'
  return (
    <PlotlyChart
      data={data}
      layout={{
        height,
        margin: { l: 55, r: 15, t: 20, b: 45 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: fg, size: 12, family: 'Inter, system-ui, sans-serif' },
        hoverlabel: { font: { family: 'Inter, system-ui, sans-serif' } },
        transition: { duration: 350, easing: 'cubic-in-out' },
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
