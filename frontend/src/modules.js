export const MODULES = [
  { id: 'antena', label: 'Antena', subtitle: 'Caracterización con VNA: S11, VSWR, impedancia y bandas GNSS', ready: true },
  {
    id: 'adquisicion', label: 'Adquisición', ready: false,
    subtitle: 'Registro NMEA en vivo de los dos receptores',
    planned: ['Estado de los puertos serie y calidad de fix', 'Skyplot y SNR por satélite', 'Sincronización por UTC y guardado de sesiones'],
  },
  {
    id: 'diferencial', label: 'Diferencial', ready: false,
    subtitle: 'Corrección en dominio de posición y métricas de error',
    planned: ['Dispersión ENU con círculos CEP antes/después', 'RMSE, CEP50/95, 2DRMS y línea base', 'Filtro de satélites comunes entre receptores'],
  },
  {
    id: 'informe', label: 'Informe', ready: false,
    subtitle: 'Experimentos y exportación de resultados',
    planned: ['Historial de experimentos', 'Exportación CSV/JSON', 'Informe PDF'],
  },
]
