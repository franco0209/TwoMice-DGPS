# TwoMice-DGPS: resumen para exponer

Guía para explicar el proyecto: qué hace, cómo está armado y, sobre todo, **cómo leer cada gráfica**.

---

## 1. En una frase

> Medimos la **antena** de dos receptores GPS Mighty Mouse con un analizador de redes (VNA) y usamos los dos receptores juntos, uno fijo (**referencia**) y otro (**móvil**), para ver **cuánto mejora la precisión** al corregir los errores comunes (GPS diferencial). Todo se procesa con una herramienta propia (backend + dashboard web).

Son dos preguntas, y cada una tiene su módulo:

| Pregunta | Módulo | Pregunta que responde |
|---|---|---|
| ¿La antena está bien adaptada a la banda GPS? | **Antena** | ¿Entra la señal a 1575.42 MHz o se refleja? |
| ¿Cuánto mejora el GPS con dos receptores? | **Adquisición → Diferencial → Informe** | ¿Cuánto baja el error de posición? |

---

## 2. Flujo general

```
 ANTENA                                   POSICIONAMIENTO
 VNA ──.s1p──► [Antena]                   Receptor ref ─┐
        S11, VSWR, Smith, Z               Receptor móvil ┴─► NMEA ──► [Adquisición] ──► sesión (.nmea + meta.json)
                                                                              │
                                                                              ▼
                                                                       [Diferencial]  ──► métricas y gráficas
                                                                              │
                                                                              ▼
                                                                         [Informe]  ──► PDF / CSV / JSON
```

La **interfaz común es el NMEA**: texto estándar que cualquier GPS entrega (`$GPGGA…`, `$GPRMC…`). Da igual de dónde venga (puerto serie real, simulador, archivo grabado o GNSS-SDR): a partir de ahí el análisis es el mismo.

**Tres orígenes de datos**
1. **Receptores NMEA reales** por puerto serie/USB.
2. **Simulación**: genera pseudorangos sintéticos y resuelve la posición; sirve para practicar y validar el análisis sin hardware.
3. **SDR (USRP / RTL-SDR)**: graba la señal de radio, **GNSS-SDR** la convierte en posición y el resultado entra como NMEA.

---

## 3. Mapa del código (qué archivo hace qué)

**Backend (Python / FastAPI)**: `backend/app/`

| Archivo | Función principal | Para qué sirve |
|---|---|---|
| `services/touchstone.py` | `parse_s1p` | Lee la medición del VNA (archivo `.s1p`) y calcula S11, VSWR, impedancia |
| `services/resonance.py` | `find_resonances`, `band_report` | Encuentra mínimos de S11, su ancho de banda a −10 dB y compara con bandas GPS/GLONASS |
| `services/nmea.py` | `EpochAssembler` | Junta las sentencias NMEA de un mismo segundo en una **época** (posición, satélites, HDOP, SNR) |
| `services/acquisition.py` | `ReceiverChannel`, `AcquisitionSession` | Un canal por receptor; la sesión guarda `ref.nmea`, `rover.nmea`, `meta.json` y emite épocas en vivo |
| `services/gnss_sim.py`, `constellation.py` | `GnssSimulator` | Simulador a nivel de pseudorango (errores comunes e independientes) |
| `services/dgps.py` | `analyze` | **El corazón**: alinea épocas, aplica la corrección diferencial y calcula errores |
| `services/stats.py` | `horizontal_metrics`, `bootstrap_ci` | CEP50/95, 2DRMS, RMSE y intervalos de confianza |
| `services/report.py` | | Genera el informe PDF |
| `services/sdr.py`, `gnsssdr.py` | `capture_check`, `GnssSdrProcess` | Valida el SDR y lanza GNSS-SDR para obtener NMEA |
| `routers/*.py` | | Endpoints REST/WebSocket (`/api/vna`, `/api/gps`, `/api/analysis`, `/api/reports`, `/api/sdr`) |

**Frontend (React + Plotly)**: `frontend/src/views/`

| Vista | Archivo | Qué muestra |
|---|---|---|
| Antena | `AntennaView.jsx` | Curvas del VNA y comparación unidad 1 vs 2 |
| Adquisición | `AcquisitionView.jsx` (asistente), `AcquisitionLive.jsx` (KPIs y gráficas), `SdrSteps.jsx`, `Guide.jsx` | Asistente guiado paso a paso y vista en vivo |
| Diferencial | `DifferentialView.jsx` + `components/DgpsResult.jsx` | Resultados antes/después de la corrección |
| Informe | `ReportView.jsx` | Descarga y historial |

---

## 4. Cómo funciona el GPS diferencial (la idea central)

**Problema.** Un GPS solo da la posición con un error de varios metros. Gran parte de ese error es **el mismo para dos receptores cercanos**: la ionosfera, la troposfera, y los errores del reloj y de las órbitas de los satélites.

**Idea.** Si una referencia está en un punto **cuya posición conocemos**, ella puede *medir* cuánto se equivoca el GPS en este momento y en esta zona. Ese error se resta al móvil.

```
Δ(t)              = posición_conocida_ref − posición_medida_ref(t)
móvil_corregido(t) = posición_medida_móvil(t) + Δ(t)
```

**Qué se cancela y qué no**

| Se cancela (errores comunes) | No se cancela (errores propios de cada receptor) |
|---|---|
| Ionosfera y troposfera | **Multitrayecto** (reflejos cerca de cada antena) |
| Error de reloj y órbita del satélite | Ruido del receptor |
| | Reloj del receptor |

Por eso el montaje físico importa tanto: cielo abierto, sin metales cerca, antenas a la misma altura.

**Condición clave: el mismo conjunto de satélites.** La corrección solo vale si ambos receptores usaron **los mismos satélites** en ese instante. Si no, los errores no son comunes y la corrección puede empeorar el resultado. El software compara los satélites usados (sentencia GSA) y **descarta** las épocas con conjuntos distintos, y lo informa en pantalla.

**Cómo se calcula (`dgps.analyze`)**: alinea épocas por hora UTC → conserva las que tienen el mismo conjunto de satélites → pasa todo a coordenadas locales Este/Norte/Arriba (ENU) → aplica Δ → calcula métricas **sobre las mismas épocas** para la comparación justa «1 receptor vs diferencial».

---

## 5. Cómo leer cada gráfica

### 5.1 Módulo Antena

El VNA mide cuánta potencia **se refleja** de vuelta. Una buena antena en su banda refleja poco.

**S11 (dB)**
- **Eje X:** frecuencia (MHz). **Eje Y:** S11 en dB. Líneas verticales punteadas marcan las bandas GPS/GLONASS; la línea horizontal punteada es −10 dB.
- **Cómo leerla:** más **negativo = mejor** (menos reflexión). Referencia: **−10 dB ≈ 10 % de potencia reflejada**; es el criterio habitual de «adaptada».
- **Qué mirar:** que la curva esté **por debajo de −10 dB en 1575.42 MHz** y cuánto ancho tiene esa zona (ancho de banda a −10 dB).
- **Ojo:** en una antena activa, esa curva refleja sobre todo la **salida del amplificador (LNA)**, no la resonancia del parche. Una curva ancha y plana es normal y no significa «resonancia» en sentido estricto.

**VSWR**
- Es el mismo dato que S11 expresado como razón: **1 = perfecta**, **2 ≈ −9.5 dB** (la línea «VSWR 2» marca el límite aceptable). Se usa porque es lo que se suele citar en hojas de datos.
- **Cómo leerla:** valores cercanos a 1 en la banda = buena adaptación. Se recorta a 10 por legibilidad.

**Carta de Smith (Γ)**
- Dibuja el coeficiente de reflexión como una trayectoria en el plano complejo. **El centro es la adaptación perfecta (50 Ω)**; cuanto más lejos del centro, más reflexión.
- **Mitad superior = comportamiento inductivo; inferior = capacitivo.** Una antena resonante hace un **lazo** que pasa cerca del centro.
- **Cómo leerla:** que la curva pase **dentro de un círculo pequeño alrededor del centro** en la frecuencia GPS.

**Impedancia (Ω)**
- Dos curvas: **R** (parte resistiva) y **X** (reactiva). En 1575.42 MHz lo ideal es **R ≈ 50 Ω y X ≈ 0**. Donde X cruza por cero hay resonancia.

**Tabla «Bandas GNSS»** y **tabla «Resonancias»**
- Bandas: S11 y VSWR **justo en la frecuencia de cada banda**, con el estado «Adaptada» o «Fuera de −10 dB». Es la tabla resumen que va al informe.
- Resonancias: cada mínimo de S11 detectado, su ancho de banda a −10 dB y qué bandas cubre.

**Comparación unidad 1 vs 2** (si se cargan dos mediciones)
- **S11 y VSWR superpuestos:** una curva por unidad; si coinciden, las antenas son equivalentes.
- **ΔS11 (unidad 2 − unidad 1):** la diferencia en dB. **Cerca de 0 = unidades similares**; picos indican que una desentona en esa frecuencia (tolerancia de fabricación o desgaste).

---

### 5.2 Módulo Adquisición (en vivo)

**Indicadores (KPIs).** Por receptor: si hay **fix 3D**, cuántos satélites usa, HDOP y hora UTC. Además:
- **Satélites en común (ahora):** cuántos usan ref y móvil a la vez.
- **Épocas con mismo conjunto:** el % de épocas donde ambos usaron exactamente los mismos satélites. **Es la condición del diferencial: cuanto más alto, más épocas utilizables.**

**Skyplot** (el «cielo visto desde arriba»)
- **Centro = cenit** (justo encima); **borde = horizonte**. Los puntos cardinales N/E/S/O están en el borde. La distancia al centro es **90° − elevación**.
- Círculos = referencia, rombos = móvil. **Opacidad baja = el satélite está en vista pero sin rastrear** (sin señal medible).
- **Qué mirar:** satélites **repartidos** por el cielo = buena geometría; todos agrupados = geometría pobre (HDOP alto). Los de baja elevación (cerca del borde) son más susceptibles al multitrayecto.

**SNR por satélite (dB-Hz)**
- Barras por satélite, una por receptor. **Más alto = señal más fuerte.** Como referencia general, ~40 dB-Hz o más es señal buena y por debajo de ~30 es débil.
- **Qué mirar:** que ref y móvil tengan barras parecidas. Si el móvil tiene mucho menos, su antena o su entorno es peor, y eso baja el diferencial.

**Dispersión de posición (m)**
- Cada punto es una posición medida, **relativa a la media de cada receptor**. Este = horizontal, Norte = vertical, con escala igual en ambos ejes.
- **Cómo leerla:** una **nube compacta y redonda = receptor preciso**; una nube **alargada** suele indicar mala geometría (HDOP alto). Aquí se compara cada receptor consigo mismo, **todavía sin corregir**.

**Satélites usados y HDOP**
- Línea continua = nº de satélites (eje izquierdo); línea punteada = **HDOP** (eje derecho, 0–5).
- **HDOP bajo es mejor** (< 2 muy bueno; > 5 pobre). Si HDOP sube cuando bajan los satélites, la geometría se está degradando.

**Captura de prueba del SDR (asistente SDR)**
- **Espectro de la captura:** potencia vs frecuencia alrededor de 1575.42 MHz. Sirve para comprobar que **llega señal**, que **no está saturada** y que no hay un tono de interferencia (un pico muy alto). La señal GPS está por debajo del ruido: **no se ve como un pico**. Lo que se valida es el nivel, la saturación y que el piso suba al conectar la antena alimentada.

---

### 5.3 Módulo Diferencial (el resultado principal)

**Tarjetas superiores.** CEP50, CEP95 y 2DRMS, cada una como «**1 receptor → diferencial**» con el % de mejora y su intervalo de confianza.
- **CEP50:** radio del círculo que contiene el **50 %** de las posiciones (mediana del error horizontal).
- **CEP95:** radio que contiene el **95 %**.
- **2DRMS:** ≈ 2 × el error cuadrático medio horizontal; cubre aprox. el 95–98 %.
- **Épocas con el mismo conjunto:** cuántas se usaron y cuántas se descartaron.

> **Aviso importante.** Si no se indica la posición real del móvil, las cifras miden **precisión** (qué tan agrupadas están las posiciones) y no **exactitud** (qué tan cerca están de la verdad). La pantalla lo advierte en un recuadro. Una referencia con coordenadas mal conocidas **sesga todo el experimento**.

**Dispersión horizontal con círculos CEP**
- Nube **naranja = 1 receptor**, nube **azul = diferencial**, con los círculos CEP50 y CEP95 de cada una. El centro es la posición de referencia.
- **Cómo leerla:** si el diferencial funciona, la **nube azul es más pequeña y está más cerca del centro**, y sus círculos son menores. Si ambas nubes se parecen, la corrección no está aportando (errores no comunes dominantes, por ejemplo multitrayecto).

**Histograma del error horizontal**
- Cuántas épocas tuvieron cada error (m). Naranja = 1 receptor, azul = diferencial, superpuestos.
- **Cómo leerlo:** el diferencial debe quedar **desplazado hacia la izquierda** (errores más pequeños) y **más estrecho**. Una cola larga a la derecha indica episodios malos puntuales.

**Error Este / Norte / Arriba vs tiempo (min)**
- Tres gráficas, una por componente: el error de cada época en el tiempo, con y sin corrección.
- **Cómo leerlas:** el error de 1 receptor suele tener **derivas lentas** (ionosfera, reloj de satélite): es la parte común. En la serie diferencial esa deriva **desaparece** y queda solo el ruido rápido (multitrayecto y ruido del receptor), que no se puede cancelar. La componente **vertical suele ser la peor**, y es normal.

**Tabla de métricas**
- Filas: RMSE, CEP50, CEP95, 2DRMS, RMSE vertical, **sesgo** horizontal, σ Este/Norte y CEP50 de precisión. Columnas: 1 receptor, IC 95 %, diferencial, IC 95 %, mejora.
- **Sesgo vs σ:** el diferencial reduce sobre todo el **sesgo** (error sistemático). La dispersión σ mejora menos, porque viene de errores independientes.
- **IC 95 % (bootstrap por bloques):** el rango en que está el valor verdadero con 95 % de confianza. Las muestras consecutivas están **correlacionadas**, así que 3600 muestras no valen por 3600 independientes; por eso se remuestrean **bloques**. **Si el intervalo de la mejora no incluye 0, la mejora es estadísticamente real.** La nota inferior da también la autocorrelación del error antes y después.

**Línea base referencia → móvil**
- Compara la **distancia estimada entre los dos receptores** con 1 receptor y con diferencial, frente a la distancia **real medida con cinta**.
- **Cómo leerla:** es una métrica **independiente de la posición absoluta**. Si el diferencial funciona, la línea base estimada es **más cercana a la real y varía menos (σ más baja)**. Es la prueba más limpia de que el sistema funciona.

---

### 5.4 Módulo Informe
- **PDF, CSV y JSON** del análisis actual (el PDF puede incluir la caracterización de la antena).
- **Historial de experimentos:** tabla para comparar sesiones (por ejemplo distintas horas del día).

---

## 6. Guion corto de exposición

1. **Problema:** el GPS comercial da errores de metros. ¿Se puede reducir con dos receptores?
2. **Antena:** con el VNA comprobamos que la antena está adaptada a 1575.42 MHz (S11, VSWR, Smith). Hay que aclarar que, siendo antena activa, medimos principalmente el LNA.
3. **Montaje:** referencia en punto conocido, móvil a una distancia medida con cinta, cielo abierto.
4. **Diferencial:** la referencia mide su propio error y se lo resta al móvil, **solo cuando usan los mismos satélites**.
5. **Resultado:** mostrar la **dispersión con círculos CEP** y la **línea base**: dos gráficas que se entienden sin explicación técnica. Respaldar con la tabla de métricas y sus IC95.
6. **Límites:** el diferencial **no** cancela el multitrayecto ni el ruido propio del receptor, y no es mejor que la posición «conocida» de la referencia.

## 7. Preguntas que pueden hacerte

| Pregunta | Respuesta breve |
|---|---|
| ¿Por qué mejora solo parcialmente? | Cancela errores **comunes**; el multitrayecto y el ruido son propios de cada antena. |
| ¿Por qué se descartan épocas? | Si los receptores usaron satélites distintos, los errores no son comunes y la corrección podría empeorar. |
| ¿Qué es CEP50 vs CEP95? | Radios que contienen el 50 % y el 95 % de las posiciones. |
| ¿Precisión o exactitud? | Precisión = agrupamiento; exactitud = cercanía a la verdad. El diferencial mejora sobre todo el **sesgo**. |
| ¿Por qué un intervalo de confianza con bloques? | El error está autocorrelacionado; remuestrear puntos sueltos daría un intervalo demasiado optimista. |
| ¿Por qué −10 dB? | Es el criterio habitual: menos del 10 % de la potencia se refleja. |
| ¿Por qué el S11 de una antena activa es plano? | Se mide la salida del LNA, no el parche radiante. |
| ¿Y el modo SDR? | En lugar de un módulo GPS cerrado, grabamos la señal de radio y GNSS-SDR calcula la posición; sigue entrando como NMEA. Solo **recepción**, nunca se transmite. |

## 8. Estado y límites (decir con honestidad)
- La caracterización de antena y el análisis diferencial están implementados y probados con **datos simulados y una medición de VNA**.
- El **modo real con los dos Mighty Mouse** y el **modo SDR con hardware** aún no se han validado con equipos conectados.
- Los parámetros del simulador son plausibles, **no calibrados** con el Mighty Mouse.
- El diferencial se hace en el **dominio de la posición** (con NMEA), no sobre observaciones crudas; una mejora futura sería usar pseudorangos o fase (RTKLIB).
