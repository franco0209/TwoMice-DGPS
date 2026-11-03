# TwoMice-DGPS

**Caracterización de antena con VNA y GPS diferencial con dos Mighty Mouse 3GPS**

Curso: Comunicaciones Satelitales – Laboratorio C
Integrantes: Franco Jesus Cahua Soto · Elisban Huamani Quispe

---

## 1. Resumen

El proyecto tiene dos partes que se conectan entre sí:

1. **Caracterización RF.** Con un Analizador Vectorial de Redes (VNA) se mide la antena activa de los receptores Mighty Mouse 3GPS (S11, impedancia, VSWR) para hallar su frecuencia de resonancia, su ancho de banda y su adaptación en la banda GPS.
2. **Posicionamiento diferencial.** Con dos receptores (uno de referencia en una posición conocida y otro móvil) se cuantifica cuánto mejora la precisión respecto a usar un solo receptor.

El resultado es doble: **un informe experimental** y **una herramienta de software reproducible** (backend + frontend) que procesa las mediciones y calcula las métricas.

## 2. Objetivos

**General.** Caracterizar el sistema antena/receptor Mighty Mouse 3GPS y evaluar experimentalmente cuánto mejora la precisión de posicionamiento al emplear dos unidades en configuración diferencial.

**Específicos**
1. Documentar las características eléctricas de la antena activa.
2. Medir con el VNA S11, impedancia y VSWR en un barrido que incluya la banda GPS.
3. Determinar frecuencias de resonancia y ancho de banda útil, y compararlos con las bandas GNSS.
4. Medir la precisión base con un solo receptor.
5. Medir con dos receptores (referencia + móvil) y cuantificar la mejora.
6. Entregar una metodología y un software que permitan repetir el análisis.

**Criterios de éxito (propuestos)**

| Parte | Criterio |
| --- | --- |
| Antena | S11 ≤ −10 dB (VSWR ≤ 2) en torno a 1575.42 MHz, con el ancho de banda medido y reportado |
| Antena | Diferencias entre la unidad 1 y la unidad 2 cuantificadas |
| Posicionamiento | CEP50, CEP95 y 2DRMS calculados para 1 receptor y para el caso diferencial, con el porcentaje de mejora |
| Software | Un `.s1p` y un log NMEA producen el informe completo sin intervención manual |

## 3. Puntos críticos del diseño experimental

Estos puntos salen del análisis del plan original. Conviene resolverlos antes de medir.

### 3.1 Qué mide realmente el VNA en una antena activa
Una antena activa lleva un LNA entre el elemento radiante (el parche) y el cable. Midiendo S11 desde el conector del cable se ve sobre todo **la adaptación de salida del LNA**, no la resonancia del parche, y esa respuesta suele ser ancha y plana. Por eso la "frecuencia de resonancia de la antena" no se obtiene directamente de ese S11. Opciones, de más a menos recomendable:

| Opción | Qué se mide | Observación |
| --- | --- | --- |
| **A. Parche pasivo accesible** | S11 del elemento radiante (abriendo la carcasa o con el LNA desconectado) | Da la resonancia real. Es destructivo o delicado: confirmar que es viable |
| **B. S21 con antena de referencia** | Respuesta en frecuencia de transmisión entre una antena de referencia y la del Mighty Mouse | Caracteriza el conjunto parche + LNA en la banda real. Requiere alimentar la antena activa |
| **C. S11 en el conector, con alimentación** | Adaptación de salida del conjunto | Útil como dato de adaptación en la banda, pero no es la resonancia del parche |

Se recomienda hacer **C como línea base** y **A o B** para identificar la resonancia. Si solo se hace C, hay que escribir en el informe qué representa ese dato.

### 3.2 Alimentación DC por el cable (riesgo para el VNA)
Las antenas activas reciben su polarización (típicamente 3–5 V) por el mismo cable coaxial. Conectarlas directamente a un puerto del VNA puede **dañarlo**. Usar un *bias-tee* (alimentación inyectada fuera del VNA) o un bloqueador de DC en el puerto, y verificar la tensión de alimentación del receptor antes de conectar. Si se mide sin alimentar, el LNA queda sin polarizar y su respuesta no es la de operación.

### 3.3 Qué frecuencias esperar
La hipótesis de trabajo (a confirmar con la hoja de datos del Mighty Mouse) es que el receptor es de **una sola banda, GPS L1 a 1575.42 MHz**. En ese caso:
- Las resonancias en L2 (1227.6 MHz) o L5 (1176.45 MHz) no deberían existir en un parche L1. El objetivo de buscar "otras frecuencias resonantes" se replantea como **detectar respuestas adicionales (armónicos, modos superiores, espurios) y verificar el rechazo fuera de banda**.
- Si el receptor fuese multibanda, la lista de bandas a comparar ya está implementada en el software (`GNSS_BANDS`).

### 3.4 Barrido y calibración del VNA
- Barrido sugerido: **1.0 – 2.0 GHz**, al menos 801 puntos (para ver el ancho de banda con detalle). Un segundo barrido amplio (p. ej. 0.5 – 3 GHz) sirve para detectar respuestas adicionales.
- Calibración **SOL** (Short-Open-Load) en el **plano del conector** donde se conecta la antena, con el mismo cable que se usará en la medición. Anotar fecha, kit y modelo de VNA.
- Medir en un entorno despejado: objetos metálicos cercanos desplazan la respuesta de una antena.

### 3.5 Límite del diferencial con salida NMEA
Con salida NMEA solo se puede hacer **diferencial en el dominio de la posición**: la referencia calcula `Δ = posición_conocida − posición_medida` y esa corrección se resta al móvil. Esto solo funciona bien si **ambos receptores usan el mismo conjunto de satélites** en cada instante; si no, los errores no son comunes y la corrección no los cancela (puede empeorar el resultado). Por eso el software:
- Registra los satélites usados (mensaje GSA) y **solo aplica la corrección en épocas con el mismo conjunto** (o reporta cuántas se descartan).
- Mantiene como mejora futura el diferencial sobre observaciones crudas (pseudorangos/fase) con RTKLIB, si el receptor las entrega.

### 3.6 Posición "conocida" de la referencia
La calidad del diferencial no puede superar la calidad de la posición de referencia. Opciones: punto con coordenadas oficiales cercano, posicionamiento largo (horas de promedio) con post-proceso, o coordenadas de una estación de referencia de una red geodésica si hay una cercana. Un punto leído de un mapa en línea puede tener errores de metros y **sesgar** todo el experimento. Documentar el método y la incertidumbre asumida.

### 3.7 Exactitud vs. precisión
- **Precisión:** dispersión de las muestras alrededor de su propia media (desviación estándar, CEP respecto a la media).
- **Exactitud:** distancia respecto a la posición verdadera (incluye el sesgo).
El diferencial mejora sobre todo el **sesgo** común (atmósfera, reloj, efemérides); la dispersión por multitrayecto y ruido de cada receptor no se cancela. El informe debe separar ambos efectos.

### 3.8 Métrica adicional recomendada: línea base
Si los dos receptores se fijan a una distancia medida con cinta (p. ej. 2–5 m), la **longitud de la línea base** estimada frente a la real es una métrica independiente de la posición absoluta y no requiere conocer coordenadas con precisión. Complementa al CEP.

### 3.9 Diseño estadístico de las sesiones
- Las muestras consecutivas están **autocorrelacionadas**: 3600 muestras a 1 Hz no equivalen a 3600 muestras independientes. Reportar intervalos de confianza por *bootstrap por bloques* o comparar entre sesiones.
- Sesiones de al menos **1 hora**, repetidas en **momentos distintos del día** (la geometría satelital cambia; se repite cada ~23 h 56 min).
- Cielo despejado, mismo montaje, misma altura de antena; registrar HDOP, número de satélites y SNR, y anotar condiciones (clima, obstáculos).
- Receptores encendidos varios minutos antes de registrar (convergencia del fix).

## 4. Metodología

| Etapa | Actividad | Resultado |
| --- | --- | --- |
| 1 | Inspección y documentación de los dos Mighty Mouse y sus antenas (fotos, hoja de datos, tensión de alimentación) | Ficha técnica de cada unidad |
| 2 | Calibración SOL del VNA y montaje con bias-tee/bloqueador DC | Sistema listo para medir |
| 3 | Barrido de S11 (y S21 con antena de referencia si aplica); exportar `.s1p` | Curvas S11, VSWR, impedancia |
| 4 | Identificación de mínimos de S11 y ancho de banda a −10 dB | Frecuencias de resonancia |
| 5 | Comparación con las bandas GPS/GNSS del receptor | Banda de operación caracterizada |
| 6 | Posicionamiento con un receptor (sesiones ≥ 1 h) | Error base (CEP, RMSE, 2DRMS) |
| 7 | Posicionamiento con dos receptores: referencia en posición conocida + móvil, registro simultáneo | Datos diferenciales |
| 8 | Comparación estadística: error, estabilidad, repetibilidad, línea base | Mejora experimental obtenida |

**Parámetros a registrar (VNA):** frecuencia, S11 (dB), R + jX, VSWR, ancho de banda a −10 dB, frecuencia central de cada resonancia.
**Parámetros a registrar (GPS):** timestamp UTC, lat, lon, altura, tipo de fix, satélites usados, HDOP, SNR por satélite.

## 5. Equipos
- 2 × Mighty Mouse 3GPS con antena activa
- 1 × VNA (modelo por definir) y kit de calibración SOL
- Bias-tee o bloqueador de DC compatible con 1–2 GHz
- Antena de referencia (para la opción B de 3.1), si se dispone
- 2 × puertos serie/USB para los receptores y una PC
- Cables y adaptadores RF, alimentación, soportes y trípodes, cinta métrica

## 6. Resultados esperados
1. Ficha y curvas de cada antena (S11, VSWR, impedancia), con resonancias, ancho de banda y cobertura de bandas GNSS.
2. Tabla comparativa **1 receptor vs. 2 receptores** (RMSE, CEP50/95, 2DRMS, estabilidad, repetibilidad) con el porcentaje de mejora y su incertidumbre.
3. Una metodología reproducible y el software que la implementa.

## 7. Software

### Arquitectura
```
Frontend (React + Vite)  <--REST/WebSocket-->  Backend (FastAPI, Python)  -->  SQLite + archivos
   Plotly / Leaflet                             numpy, scipy, pandas,
                                                pynmea2, pyserial, pyproj
```

### Módulos
| Módulo | Función | Estado |
| --- | --- | --- |
| **VNA** | Importa `.s1p`/CSV; calcula S11, VSWR, impedancia; detecta resonancias y ancho de banda; compara con bandas GNSS | Backend hecho |
| **Adquisición GPS** | Lee dos puertos serie, parsea NMEA (GGA, RMC, GSA, GSV), sincroniza por UTC, guarda sesiones, transmite en vivo | Pendiente |
| **Análisis diferencial** | Convierte a ENU, aplica la corrección en dominio de posición (con filtro de mismo conjunto de satélites), calcula RMSE, CEP50/95, 2DRMS, estabilidad, línea base | Pendiente |
| **Reportes** | Experimentos, exportación CSV/JSON, informe PDF | Pendiente |

### Vistas del frontend
Antena (S11, VSWR, Smith, tabla de resonancias, comparación unidad 1 vs. 2) · Adquisición (estado en vivo, skyplot, SNR) · Diferencial (dispersión con círculos CEP antes/después, series de error, histogramas, mapa) · Informe.

### Estructura del repositorio
```
TwoMice-DGPS/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/        # vna.py (hecho); gps.py, analysis.py, reports.py (pendientes)
│   │   └── services/       # touchstone.py, resonance.py (hechos); nmea_reader.py, dgps.py, stats.py
│   ├── tests/
│   └── requirements.txt
├── frontend/               # React + Vite (pendiente)
├── data/                   # ejemplos .s1p y logs NMEA
└── README.md
```

### API actual
- `GET /api/health`
- `POST /api/vna/analyze` — recibe un `.s1p` y devuelve S11, VSWR, impedancia, resonancias y reporte por banda.

### Ejecución del backend
```
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

## 8. Hoja de ruta
- [x] Backend VNA: parser Touchstone, S11/VSWR/Z, resonancias, bandas GNSS
- [ ] Frontend: carga de `.s1p` y gráficas S11/VSWR con bandas GPS
- [ ] Validar el parser con una medición real del VNA del laboratorio
- [ ] Adquisición NMEA de dos receptores y registro de sesiones
- [ ] Diferencial en dominio de posición con filtro de satélites comunes
- [ ] Métricas: RMSE, CEP50/95, 2DRMS, línea base, bootstrap por bloques
- [ ] Informe PDF
- [ ] (Opcional) Diferencial con datos crudos vía RTKLIB; lectura en vivo del VNA por SCPI

## 9. Preguntas abiertas
- ¿Qué modelo de VNA se usará y qué formato exporta?
- ¿El Mighty Mouse entrega solo NMEA o también datos crudos? ¿A qué baudios y tasa de actualización?
- ¿Es posible acceder al parche pasivo (opción A) o se medirá S21 (opción B)?
- ¿Cómo se obtendrá la posición conocida de la referencia?
