# Manual de uso – TwoMice-DGPS

Herramienta para caracterizar la antena de los receptores Mighty Mouse 3GPS con un VNA y medir cuánto mejora la precisión con dos receptores en modo diferencial.

Flujo general:

```
1. Antena       -> cargar los .s1p del VNA (unidad 1 y 2) y compararlos
2. Adquisición  -> registrar NMEA de los dos receptores (o simular)
3. Diferencial  -> calcular la mejora (CEP50/95, 2DRMS, RMSE, línea base)
4. Informe      -> descargar PDF / CSV / JSON
```

---

## 1. Instalación y arranque

Requisitos: Python 3.11+ y Node.js 20+.

**Backend** (una vez):
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
**Arrancar el backend** (terminal 1):
```
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```
**Frontend** (terminal 2):
```
cd frontend
npm install        # solo la primera vez
npm run dev
```
Abra **http://localhost:5173**. El backend debe estar en el puerto 8000; si no, las vistas muestran «No se pudo contactar al backend».

Pruebas del backend (opcional): `cd backend && pytest`.

---

## 2. Módulo Antena (VNA)

### 2.1 Medir con el VNA
- Barrido sugerido: **1.0–2.0 GHz**, mínimo 801 puntos. Un barrido amplio (0.5–3 GHz) sirve para ver respuestas adicionales.
- Calibre **SOL** (Short-Open-Load) en el plano del conector, con el mismo cable de la medición.
- **Cuidado con la alimentación DC**: la antena activa se polariza por el coaxial (3–5 V). Use un *bias-tee* o bloqueador de DC; conectarla directo al puerto puede dañar el VNA.
- Mida en un entorno despejado, sin metales cerca.
- Exporte en formato Touchstone **`.s1p`**.
- Recuerde qué mide: S11 en el conector de una antena activa refleja sobre todo la adaptación del LNA, no la resonancia del parche (ver README §3.1).

### 2.2 Cargar y leer los resultados
1. Entre a **Antena** y elija la pestaña **Unidad 1** o **Unidad 2**.
2. Arrastre el `.s1p` a la zona punteada o haga clic para elegirlo. Para probar use `data/ejemplo_sintetico.s1p`.
3. Verá:
   - **Indicadores**: bandas adaptadas (S11 ≤ −10 dB), mejor resonancia, S11/VSWR en GPS L1 y L2.
   - **Gráficas**: S11, VSWR, carta de Smith e impedancia (R y X), con las bandas GNSS marcadas.
   - **Tablas**: estado por banda GNSS y resonancias (frecuencia, S11, VSWR, impedancia, ancho de banda a −10 dB).
4. «Cambiar archivo» reemplaza la medición de esa unidad.

Criterio de éxito propuesto: **S11 ≤ −10 dB (VSWR ≤ 2) en torno a 1575.42 MHz**.

### 2.3 Comparar unidades
Con ambas cargadas, abra **Comparar 1 vs. 2**: curvas superpuestas, diferencia de S11 (unidad 2 − unidad 1) y tabla comparativa por banda y de la mejor resonancia.

Los análisis se conservan al cambiar de módulo y se pierden al recargar la página.

---

## 3. Módulo Adquisición (GPS)

Registra los dos receptores a la vez: **Referencia** (en posición conocida) y **Móvil**. Cada sesión guarda `ref.nmea`, `rover.nmea` y `meta.json` en `data/sessions/<id>/`.

La adquisición es un **asistente guiado**: cada etapa indica qué hacer, valida el resultado y no deja avanzar hasta que pasa. Al terminar la sesión salta sola al cierre, con acceso al análisis diferencial.

### 3.1 Modo simulación (para probar sin hardware)
Pasos: **Origen → Backend → Escenario → Registrar → Cierre**.
1. Elija **Simulación**; se valida la conexión con el backend.
2. Escenario: duración (s), velocidad (× tiempo real; 0 = lo más rápido), línea base (m), offset de C/N0 del móvil (dB) y semilla.
3. **Iniciar registro**. Para sesiones largas use velocidad alta (p. ej. 100) o 0.

El simulador genera errores comunes (efemérides, iono, tropo) y errores independientes (multitrayecto, ruido, selección de satélites), y escribe NMEA igual que un receptor real. La constelación es sintética y los parámetros no están calibrados con el Mighty Mouse.

### 3.2 Modo real (dos puertos serie)
Pasos: **Origen → Backend → Conectar → Validar NMEA → Esperar fix → Registrar → Cierre**.
1. **Conectar**: alimente ambos receptores y conéctelos a la PC. «Buscar puertos» debe listar al menos dos; si no, indica qué revisar (cable, driver, alimentación).
2. **Validar NMEA**: asigne puerto de referencia y móvil (distintos) y baudios. «Comprobar NMEA» abre cada puerto ~3 s y verifica el checksum; distingue puerto ocupado, sin datos y baudios incorrectos.
3. **Esperar fix**: re-comprueba solo hasta que ambos tengan fix y ≥ 4 satélites (muestra calidad GGA, satélites rastreados y HDOP).
4. **Registrar**: indicadores de que llegan épocas de ambos receptores. Si un puerto se cae, la sesión se detiene y se marca el error.

Los receptores deben emitir al menos **GGA** y, para el diferencial, **GSA** (satélites usados); **RMC** (fecha/hora) y **GSV** (skyplot/SNR) son recomendables. Sin GSA no hay épocas con «mismo conjunto» y el diferencial no se puede calcular.

> El modo real está implementado pero **aún no se ha probado con los receptores físicos**. Haga primero una sesión corta de verificación.

### 3.3 Qué muestra la vista
- **Indicadores**: fix, satélites, HDOP y hora de cada receptor; satélites en común y **% de épocas con el mismo conjunto** (condición del diferencial).
- **Skyplot**, **SNR por satélite**, **dispersión de posición** y **satélites usados + HDOP** en el tiempo.
- **Detener** finaliza y guarda la sesión (`meta.json` se escribe al terminar).

---

## 4. Módulo Diferencial

Calcula la mejora de la corrección en dominio de posición.

### 4.1 Cómo se calcula
1. Se alinean las épocas por UTC y se conservan las que tienen fix en ambos receptores.
2. Se usan solo las épocas donde ambos emplearon **el mismo conjunto de satélites**; el resto se descarta y se informa.
3. Corrección: `Δ = −(ref_medida − ref_conocida)` y `móvil_corregido = móvil_medido + Δ`.
4. «1 receptor» y «diferencial» se comparan sobre **las mismas épocas**.

### 4.2 Fuente de datos
**Sesión guardada** (la habitual):
- Elija la sesión en la lista.
- *Simulación*: puede dejar las posiciones vacías; se usa la verdad exacta.
- *Real*: **obligatorio** indicar la **posición conocida de la referencia** (latitud, longitud en grados y **altura elipsoidal** en metros; no la altura sobre el nivel del mar).

**Subir logs .nmea**: cargue el log de la referencia y el del móvil (por ejemplo, grabados con un terminal serie) e indique la posición conocida de la referencia.

**Posición verdadera del móvil (opcional)**:
- Con ella se mide **exactitud** (incluye el sesgo).
- Sin ella solo se mide **precisión** (dispersión respecto a su propia media). Aparece un aviso en pantalla y en el PDF.

**Remuestreos bootstrap / bloque**: 500 remuestreos por defecto; deje el bloque vacío para que se elija automáticamente según la autocorrelación. Ponga 0 remuestreos para omitir los intervalos de confianza.

Pulse **Calcular diferencial**.

### 4.3 Cómo leer el resultado
- **Indicadores**: CEP50, CEP95 y 2DRMS antes → después, % de mejora con su IC 95 %, y % de épocas con el mismo conjunto.
- **Dispersión horizontal** con círculos CEP50 (discontinuo) y CEP95 (continuo) para cada caso.
- **Histograma** del error horizontal y **series de error** Este, Norte y Vertical.
- **Tabla de métricas**: RMSE, CEP50/95, 2DRMS con IC 95 %, RMSE vertical, sesgo, σ y CEP de precisión.
- **Línea base** ref → móvil, con 1 receptor y diferencial; con verdad del móvil, también el error RMS frente a la longitud real.

Cómo interpretar:
- **CEP50/CEP95**: radio que contiene el 50 % / 95 % de las épocas. **2DRMS** = 2·RMSE horizontal.
- Si el **IC 95 % de la mejora incluye valores negativos**, la mejora no es estadísticamente clara con esos datos; registre más tiempo.
- El diferencial reduce el **sesgo común** (atmósfera, reloj, efemérides). El multitrayecto y el ruido de cada receptor no se cancelan.
- Pocas épocas con «mismo conjunto» (por ejemplo < 30 %) dan resultados poco fiables: alargue la sesión.
- La incertidumbre de la posición de referencia se traslada al resultado. Una referencia mal ubicada produce un sesgo en todo el experimento.

---

## 5. Módulo Informe

- **Informe del análisis actual**: descarga el **PDF** del último cálculo hecho en Diferencial. Marque «Incluir S11/VSWR de la antena» para añadir la página de la antena (usa la unidad 1, o la 2 si solo está cargada esa). También puede bajar el **JSON** del análisis.
- **Historial de experimentos**: lista las sesiones guardadas. Las ya analizadas muestran CEP50 antes → después, mejora y % de mismo conjunto, con enlaces a **PDF**, **CSV** (series de error por época) y **JSON**.

Los resultados se guardan como `analysis.json` dentro de la carpeta de la sesión al calcular una sesión guardada (no al analizar archivos subidos).

---

## 6. Procedimiento recomendado en el laboratorio

1. **Antena**: calibre el VNA, mida la unidad 1 y la 2 con bias-tee, cárguelas y compare. Compruebe S11 ≤ −10 dB en L1.
2. **Posición de referencia**: determine las coordenadas del punto con la mejor calidad posible (punto oficial o promedio largo con post-proceso) y anote la altura **elipsoidal**. Documente el método y su incertidumbre.
3. **Prueba corta** en Adquisición (2–3 min, modo real) para verificar puertos, baudios y que lleguen GGA y GSA.
4. **Sesión larga** con el móvil fijo en un punto de línea base conocida; cuanto más tiempo, mejor (varias decenas de minutos o horas). Repita en varias horas del día si es posible.
5. **Diferencial**: calcule con la posición de la referencia y, si la conoce, la del móvil.
6. **Informe**: descargue el PDF y los CSV para el documento final.

---

## 7. Solución de problemas

| Síntoma | Causa probable y solución |
| --- | --- |
| «No se pudo contactar al backend» | `uvicorn` no está corriendo o no usa el puerto 8000. |
| «Sin conexión al backend» en Adquisición | Igual; se reconecta solo al levantar el backend. |
| Error 422 al subir el `.s1p` | Formato no soportado o archivo vacío; exporte Touchstone `.s1p`. |
| «Solo N épocas con el mismo conjunto…» | La sesión es corta o los receptores no emiten GSA. Alargue la sesión o configure GSA. |
| «No hay épocas simultáneas con fix…» | Los logs no se solapan en el tiempo UTC o falta RMC/hora. Revise relojes y mensajes. |
| «Sesión real: indique la posición conocida…» | En datos reales debe rellenar lat, lon y altura elipsoidal de la referencia. |
| Mejora negativa o nula | Mal posicionada la referencia, pocos datos, o dominan multitrayecto/ruido. Revise el sesgo de la referencia y el entorno. |
| «Ya hay una sesión en curso» | Detenga la sesión actual antes de iniciar otra. |
| No aparecen sesiones en Diferencial | Solo se listan sesiones finalizadas y guardadas; detenga la sesión y pulse «Actualizar» en Informe o recargue la vista. |

---

## 8. Dónde quedan los archivos

```
data/sessions/<id>/
├── ref.nmea       # log crudo de la referencia
├── rover.nmea     # log crudo del móvil
├── meta.json      # modo, parámetros, verdad de terreno (solo simulación)
└── analysis.json  # último análisis diferencial
```
`data/sessions/` no se sube a Git. Los logs `.nmea` pueden reanalizarse más tarde con «Subir logs .nmea».

## 9. Referencia rápida de la API

Documentación interactiva en **http://localhost:8000/docs** con el backend en marcha. Endpoints principales: `/api/vna/analyze`, `/api/gps/sessions`, `/api/analysis/run`, `/api/analysis/upload`, `/api/reports/sessions/{id}.pdf`. Detalle en el README.
