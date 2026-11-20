# Teoría del proyecto TwoMice-DGPS

Este documento reúne los conceptos necesarios para entender qué se mide, por qué se mide así y cómo se interpretan los resultados. Está ordenado de lo general a lo específico del proyecto. Para el uso del software ver `MANUAL.md`; para el diseño experimental, `README.md`.

**Índice**
1. [Cómo funciona el GPS](#1-cómo-funciona-el-gps)
2. [Fuentes de error](#2-fuentes-de-error)
3. [GPS diferencial](#3-gps-diferencial)
4. [El formato NMEA](#4-el-formato-nmea)
5. [Sistemas de coordenadas](#5-sistemas-de-coordenadas)
6. [Métricas de exactitud y precisión](#6-métricas-de-exactitud-y-precisión)
7. [Estadística: autocorrelación y bootstrap por bloques](#7-estadística-autocorrelación-y-bootstrap-por-bloques)
8. [Caracterización de la antena con VNA](#8-caracterización-de-la-antena-con-vna)
9. [Antenas activas y su efecto en el receptor](#9-antenas-activas-y-su-efecto-en-el-receptor)
10. [El simulador](#10-el-simulador)
11. [Glosario](#11-glosario)

---

## 1. Cómo funciona el GPS

### 1.1 Idea básica
Cada satélite transmite su posición y la hora a la que emitió la señal. El receptor mide cuánto tardó en llegar y, multiplicando por la velocidad de la luz *c*, obtiene una distancia aparente llamada **pseudorango**.

### 1.2 Ecuación del pseudorango
Para el satélite *i*:

```
ρᵢ = rᵢ + c·(δt_rx − δtsᵢ) + Iᵢ + Tᵢ + εᵢ
```

| Término | Significado |
| --- | --- |
| `rᵢ` | distancia geométrica real receptor–satélite |
| `δt_rx` | error del reloj del receptor (desconocido) |
| `δtsᵢ` | error del reloj del satélite (corregido en parte con el mensaje de navegación) |
| `Iᵢ`, `Tᵢ` | retardos de ionosfera y troposfera |
| `εᵢ` | multitrayecto, ruido y errores residuales |

Se llama *pseudo*rango porque incluye el error del reloj del receptor, que es barato (de cuarzo) y no está sincronizado.

### 1.3 Por qué hacen falta 4 satélites
Hay 4 incógnitas: la posición (x, y, z) y el error de reloj del receptor. Cada satélite aporta una ecuación, así que se necesitan **al menos 4**. Con más satélites se resuelve por **mínimos cuadrados** (en el proyecto, ponderados por la calidad de cada señal). El resultado es el **fix** (solución de posición).

### 1.4 Geometría y DOP
La precisión no solo depende del error de cada pseudorango (**UERE**, *User Equivalent Range Error*), sino de cómo están distribuidos los satélites en el cielo. Si están todos juntos, la solución es mala en alguna dirección.

```
error de posición ≈ DOP × UERE
```

- **HDOP** (horizontal), **VDOP** (vertical), **PDOP** (3D). Se calculan de la matriz de geometría *G* (vectores unitarios receptor→satélite más una columna de unos para el reloj): `(GᵀG)⁻¹`.
- HDOP < 2 es bueno; > 5 es pobre. El GPS suele ser peor en vertical que en horizontal (VDOP > HDOP), porque todos los satélites están por encima del horizonte.

### 1.5 Elevación, acimut y skyplot
Cada satélite se ve desde el receptor con un **acimut** (0–360°, desde el norte) y una **elevación** (0–90° sobre el horizonte). El **skyplot** los dibuja en un círculo con el cenit al centro. Los satélites bajos (elevación pequeña) atraviesan más atmósfera y sufren más multitrayecto; por eso se usa una **máscara de elevación** (típico 5–15°).

### 1.6 Señales y bandas
| Banda | Frecuencia (MHz) | Comentario |
| --- | --- | --- |
| GPS L1 | 1575.42 | Código C/A civil. **La banda que usa un receptor de una sola frecuencia** |
| GPS L2 | 1227.60 | Original militar; luego señales civiles |
| GPS L5 | 1176.45 | Civil, safety-of-life |
| GLONASS L1 / L2 | ≈ 1602 / ≈ 1246 | Cada satélite con su canal de frecuencia |

La hipótesis del proyecto es que el Mighty Mouse es de una sola banda (L1). Eso implica que no puede corregir la ionosfera con dos frecuencias, y por eso la ionosfera es una fuente importante de error.

### 1.7 Relación señal/ruido: C/N0
**C/N0** (dB-Hz) mide la potencia de la señal respecto a la densidad de ruido. Valores típicos de GPS en cielo abierto: **35–50 dB-Hz**. Menor C/N0 → más ruido en el pseudorango y satélites que el receptor deja de rastrear. En NMEA aparece como el SNR del mensaje GSV.

---

## 2. Fuentes de error

Órdenes de magnitud para un receptor civil de una frecuencia (valores indicativos; varían con el día, la latitud y el entorno):

| Fuente | Magnitud típica | Naturaleza |
| --- | --- | --- |
| Efemérides y reloj del satélite | ~1–2 m | **Común** a receptores cercanos |
| Ionosfera (residual tras el modelo del receptor) | ~2–10 m, más a baja latitud y de día | **Común** si la distancia es corta |
| Troposfera (residual) | ~0.2–1 m (≈ 2.3 m cenital sin corregir) | **Común** si la distancia es corta |
| Multitrayecto | ~0.5–3 m, depende del entorno y la elevación | **Independiente** |
| Ruido del receptor | ~0.3–1 m, depende del C/N0 | **Independiente** |
| Reloj del receptor | se estima en la solución | **Independiente** |

### 2.1 Errores comunes vs. independientes
Esta es la distinción central del proyecto:

- Un **error común** afecta igual a dos receptores cercanos que ven el mismo satélite (el retardo ionosférico en el camino satélite→receptor es casi el mismo si los receptores están a metros de distancia). Se puede **restar**.
- Un **error independiente** es propio de cada receptor (el rebote de la señal en una pared cercana a una antena y no a la otra). **No se cancela**; al restar dos receptores, sus varianzas se suman.

### 2.2 Multitrayecto
La señal llega por el camino directo y por reflejos. El receptor mezcla ambas y el pseudorango se sesga. Depende de la geometría local (paredes, suelo, vehículos) y cambia lentamente cuando el satélite se mueve, por eso es un error **correlacionado en el tiempo**. En la práctica es el límite del diferencial con receptores baratos.

### 2.3 Correlación espacial
Los errores atmosféricos están muy correlacionados a pocos metros y se decorrelacionan con la distancia (del orden de 1 mm por km de línea base o más, según las condiciones). Con la **línea base corta** de este proyecto (metros) se espera una buena cancelación de la parte atmosférica.

---

## 3. GPS diferencial

### 3.1 Idea
Un receptor de **referencia** está en una posición **conocida** con precisión. Compara lo que mide con lo que debería medir y obtiene el error actual. Ese error, si es común, se resta al receptor **móvil** cercano.

### 3.2 Dos dominios de corrección
| Dominio | Qué se corrige | Requisitos |
| --- | --- | --- |
| **Pseudorango** (DGPS clásico, RTCM) | El error de cada satélite por separado | Acceso a los pseudorangos; corrección satélite a satélite |
| **Posición** (este proyecto) | El vector de error de la posición final | Solo se necesita la salida NMEA |

### 3.3 Corrección en el dominio de la posición
Con coordenadas ENU centradas en la referencia:

```
Δ = posición_conocida_ref − posición_medida_ref
móvil_corregido = móvil_medido + Δ
```

(en el software, `Δ = −error_ref`, con la verdad de la referencia como origen del ENU).

### 3.4 Por qué hace falta el mismo conjunto de satélites
Si el error de posición viene de los errores de pseudorango de **ciertos** satélites, el vector de error depende de **cuáles** satélites se usaron y de su geometría. Si la referencia usó los satélites {1, 5, 7, 9, 12} y el móvil {1, 5, 7, 9, 14}, el error en posición de cada uno responde a combinaciones distintas de errores, y restar uno al otro **puede empeorar** el resultado en lugar de mejorarlo.

Por eso el software:
1. Lee los satélites usados (mensaje **GSA**) en cada época.
2. Aplica la corrección **solo** en épocas donde ambos conjuntos son idénticos.
3. Informa el porcentaje de épocas usadas y descartadas.

Esta es la principal limitación del enfoque basado solo en NMEA. La mejora completa requiere pseudorangos o fase (RTK con RTKLIB), que queda como trabajo futuro.

### 3.5 Qué cancela y qué no
- **Cancela**: el **sesgo común** (efemérides, reloj de satélite, atmósfera) → mejora la **exactitud**.
- **No cancela** (y puede aumentar): multitrayecto y ruido propios de cada receptor → la **dispersión** puede quedar igual o crecer ligeramente.
- **Introduce**: el error de la posición conocida de la referencia. Si el punto "conocido" está mal por 3 m, **todo** el móvil se desplaza 3 m (un sesgo que ningún cálculo posterior elimina). Un punto leído de un mapa en línea puede tener errores de metros.

### 3.6 Línea base
Es la distancia entre la referencia y el móvil. Se mide con 1 receptor (móvil medido − referencia conocida) y con el diferencial. Con verdad conocida se puede evaluar cuál reproduce mejor la longitud real. Es una métrica útil porque la longitud de una línea base corta es un valor **relativo**, que el diferencial mide mucho mejor que las posiciones absolutas.

---

## 4. El formato NMEA

NMEA 0183 es texto ASCII, una "sentencia" por línea:

```
$GPGGA,123519.00,1202.7840,S,07702.5680,W,1,09,1.1,150.2,M,0.0,M,,*47
```
Empieza con `$`, lleva campos separados por comas y termina con `*` + **checksum** (XOR de los caracteres entre `$` y `*`, en hexadecimal). Una línea con checksum incorrecto se cuenta como errónea y se descarta.

### 4.1 Sentencias que usa el proyecto
| Sentencia | Aporta |
| --- | --- |
| **GGA** | Hora, latitud, longitud, calidad del fix (0 = sin fix), nº de satélites, HDOP, altura sobre el nivel del mar y separación del geoide |
| **RMC** | Fecha y hora UTC, validez (A/V), velocidad y rumbo |
| **GSA** | Tipo de fix (2D/3D), **lista de satélites usados**, PDOP/HDOP/VDOP |
| **GSV** | Satélites **a la vista**: elevación, acimut y SNR (para skyplot y SNR) |

### 4.2 Detalles que importan
- **Cuantización**: la latitud/longitud viene en grados y minutos con 4 decimales de minuto. 0.0001′ ≈ **0.19 m**: es la resolución mínima de la posición y es un límite inferior de ruido.
- **Formato**: `ddmm.mmmm` (latitud) y `dddmm.mmmm` (longitud), con hemisferio N/S/E/W; el software lo convierte a grados decimales.
- **Altura**: GGA da la altura sobre el **geoide** (nivel medio del mar, "MSL"). Para calcular distancias en un sistema geodésico hace falta la altura **elipsoidal** `h = altura_MSL + separación_del_geoide`. La posición conocida de la referencia que se introduce en el software debe ser elipsoidal.
- **Filtrado interno**: muchos receptores suavizan la posición (filtro de Kalman). Eso reduce el ruido visible y **aumenta la autocorrelación** entre épocas, y puede reducir el beneficio aparente del diferencial.
- **Sincronización**: las épocas de los dos receptores se alinean por la hora UTC del RMC/GGA, no por el reloj del PC.

---

## 5. Sistemas de coordenadas

### 5.1 Geodésicas (lat, lon, h) – WGS-84
Latitud y longitud en grados sobre el elipsoide **WGS-84** (el que usa GPS), con altura elipsoidal *h*. Es el formato de entrada y salida.

### 5.2 ECEF (x, y, z)
Cartesianas fijas a la Tierra, con el origen en el centro de masas. Se usan para los cálculos de geometría. Conversión estándar con el radio de curvatura *N* del elipsoide:

```
x = (N + h)·cosφ·cosλ
y = (N + h)·cosφ·sinλ
z = (N·(1 − e²) + h)·sinφ
```

### 5.3 ENU (Este, Norte, Arriba)
Coordenadas **locales** en metros, con el origen en un punto (aquí, la referencia). Se obtiene rotando la diferencia ECEF:

```
[E N U]ᵀ = R · (ecef − ecef_ref)
```
Es el sistema natural para hablar de errores: "2 m al este, 1 m al norte, 3 m más abajo". Los errores horizontales son (E, N) y el vertical es U.

---

## 6. Métricas de exactitud y precisión

### 6.1 Exactitud vs. precisión
- **Exactitud**: cercanía a la **posición verdadera**. Incluye el sesgo.
- **Precisión**: dispersión de las muestras alrededor de **su propia media**. No incluye el sesgo.

Un receptor puede ser muy preciso (puntos muy juntos) pero poco exacto (lejos de la verdad). El diferencial mejora sobre todo el **sesgo** común, es decir, la exactitud. Sin la verdad del móvil solo se puede evaluar precisión.

### 6.2 Error horizontal
Con errores ENU `(eₖ, nₖ)` por época *k*, el error horizontal es `rₖ = √(eₖ² + nₖ²)`.

### 6.3 Métricas
| Métrica | Definición | Interpretación |
| --- | --- | --- |
| **RMSE** | `√(media(rₖ²))` | Error cuadrático medio. Penaliza los errores grandes |
| **DRMS** | = RMSE horizontal | Distancia RMS |
| **2DRMS** | `2·DRMS` | Radio que contiene aproximadamente el **95–98 %** de las muestras (según la forma de la elipse de error) |
| **CEP50** | Mediana de `rₖ` | **Círculo de error probable**: radio que contiene el 50 % |
| **CEP95** (R95) | Percentil 95 de `rₖ` | Radio que contiene el 95 % |
| **Sesgo** | Media de (e, n, u) | Error sistemático |
| **σ** | Desviación estándar | Dispersión por eje |

Para un error gaussiano circular con desviación σ por eje: CEP50 ≈ 1.1774 σ, CEP95 ≈ 2.4477 σ, DRMS = σ√2 y 2DRMS ≈ 2.83 σ. El software usa **percentiles empíricos** para el CEP, de modo que no asume que el error es gaussiano.

### 6.4 Mejora relativa
```
mejora (%) = 100 · (métrica_antes − métrica_después) / métrica_antes
```
Positiva si el diferencial reduce el error. "Antes" = 1 receptor; "después" = diferencial, ambos **sobre las mismas épocas** para que la comparación sea justa.

### 6.5 Métricas de precisión sin sesgo
`cep50_prec` y `cep95_prec` calculan los radios alrededor de la **media** de las muestras. Permiten separar el efecto de la dispersión del de sesgo.

---

## 7. Estadística: autocorrelación y bootstrap por bloques

### 7.1 Por qué importa la autocorrelación
Las épocas consecutivas de un GPS **no son independientes**: el multitrayecto, la atmósfera y el filtro interno del receptor hacen que el error en el instante *t* se parezca al de *t+1*. La **autocorrelación de lag 1** mide cuánto (1 = idéntico, 0 = independiente).

Consecuencia: 1000 épocas correlacionadas valen estadísticamente mucho menos que 1000 independientes. Un intervalo de confianza calculado como si fueran independientes sería **demasiado optimista**.

### 7.2 Bootstrap
El **bootstrap** estima la incertidumbre de una métrica remuestreando los propios datos muchas veces, recalculando la métrica en cada remuestreo y mirando su variación. Los percentiles 2.5 % y 97.5 % de esas réplicas forman el **intervalo de confianza del 95 %**.

### 7.3 Bootstrap circular por bloques
Para series correlacionadas se remuestrean **bloques consecutivos** de épocas (no épocas sueltas), preservando la correlación dentro de cada bloque. El tamaño de bloque debe ser parecido al **tiempo de decorrelación**: el software lo estima como el primer retardo en el que la autocorrelación cae por debajo de 1/e (y se puede fijar a mano).

### 7.4 Bootstrap pareado
Antes y después se calculan sobre las mismas épocas. Se remuestrean los **mismos índices** para ambos casos, y así el intervalo de la **mejora (%)** refleja la diferencia real y no el ruido de cada serie por separado.

### 7.5 Cómo leer el resultado
- Si el IC 95 % de la mejora está **por encima de 0**, la mejora es estadísticamente clara.
- Si **incluye 0 o valores negativos**, con estos datos no se puede afirmar que el diferencial mejore. Hace falta más tiempo de registro.
- Un IC ancho indica pocas épocas útiles (sobre todo con muchas descartadas por distinto conjunto de satélites).

---

## 8. Caracterización de la antena con VNA

### 8.1 Qué es un VNA
Un **Analizador Vectorial de Redes** inyecta una señal de frecuencia barrida y mide cuánto se refleja y cuánto se transmite, en **amplitud y fase**. Para una antena (un solo puerto) interesa el parámetro **S11**.

### 8.2 Coeficiente de reflexión y S11
Si una antena de impedancia `Z` se conecta a una línea de impedancia característica `Z0` (50 Ω):

```
Γ = (Z − Z0) / (Z + Z0)       (número complejo)
S11 = Γ
S11 (dB) = 20·log10 |Γ|       (pérdida de retorno, en negativo)
```
- Antena perfectamente adaptada (`Z = Z0`) → Γ = 0 → S11 → −∞ dB.
- Circuito abierto o corto → |Γ| = 1 → S11 = 0 dB (toda la potencia se refleja).

### 8.3 VSWR
La **relación de onda estacionaria**:
```
VSWR = (1 + |Γ|) / (1 − |Γ|)
```
VSWR = 1 es adaptación perfecta; crece sin límite al desadaptarse.

### 8.4 El criterio de −10 dB
| S11 | \|Γ\| | VSWR | Potencia reflejada |
| --- | --- | --- | --- |
| −6 dB | 0.50 | 3.0 | 25 % |
| **−10 dB** | **0.316** | **1.92 ≈ 2** | **10 %** |
| −15 dB | 0.178 | 1.43 | 3 % |
| −20 dB | 0.100 | 1.22 | 1 % |

El criterio habitual de "antena adaptada" es **S11 ≤ −10 dB (VSWR ≤ 2)**, que equivale a perder solo el 10 % de la potencia por desadaptación (≈ 0.46 dB). El **ancho de banda** de la antena es el rango de frecuencias donde se cumple.

### 8.5 Impedancia y carta de Smith
De Γ se obtiene la impedancia `Z = Z0·(1+Γ)/(1−Γ) = R + jX`:
- **R** (resistencia) debería ser ≈ 50 Ω en resonancia.
- **X** (reactancia) cruza por 0 en la **resonancia**; es inductiva (X > 0) por encima o capacitiva (X < 0) por debajo.

La **carta de Smith** dibuja Γ en el plano complejo (círculo unitario). Una antena bien adaptada en la banda se ve como una curva que pasa **cerca del centro**. Un lazo que rodea el centro suele indicar una resonancia.

### 8.6 Calibración
El VNA mide también los cables y conectores. La **calibración SOL** (Short, Open, Load) usa tres cargas conocidas en el plano donde se conectará la antena para eliminar sus efectos. Debe hacerse con el mismo cable, con el rango de frecuencias y los puntos de la medición, y repetirse si cambia algo.

### 8.7 Formato Touchstone (.s1p)
Archivo de texto con una línea de opciones y filas de datos:
```
# MHz S DB R 50
1500.0   -8.2   -35.1
```
La línea `#` indica unidad de frecuencia, tipo de parámetro (S), formato de los datos (`DB`: magnitud en dB y ángulo; `MA`: magnitud lineal y ángulo; `RI`: parte real e imaginaria) y la impedancia de referencia. El software lo convierte a Γ, S11, VSWR e impedancia.

### 8.8 Resonancia
Una antena resuena donde `X ≈ 0` y la adaptación es mejor (mínimo de S11). El software detecta mínimos locales de S11 que bajan de un umbral, y calcula el ancho de banda a −10 dB alrededor de cada uno. Un parche microstrip tiene **ancho de banda estrecho** (típico del orden del 1–3 %), por eso tener la resonancia centrada en 1575.42 MHz importa.

---

## 9. Antenas activas y su efecto en el receptor

### 9.1 Qué es una antena activa
Los Mighty Mouse usan una **antena activa**: un parche (elemento radiante) más un **LNA** (amplificador de bajo ruido) integrados, que se alimenta con **3–5 V por el mismo coaxial**. El LNA sube la señal antes de que el cable la degrade y fija la figura de ruido del sistema.

### 9.2 Consecuencias para la medición
- Medir S11 en el conector del cable con el VNA mide **la salida del LNA**, no el parche. Esa respuesta es ancha y plana. La "resonancia del parche" no se observa directamente.
- Para obtener la resonancia real hay opciones (README §3.1): **A.** acceder al parche pasivo, **B.** medir **S21** con una antena de referencia (respuesta de transmisión del conjunto) o **C.** S11 en el conector (adaptación de salida). Si solo se hace C, hay que decir en el informe qué representa.
- **Riesgo de daño**: la tensión DC del receptor puede dañar el puerto del VNA. Use un **bias-tee** (alimentación inyectada fuera del VNA) o un bloqueador de DC. Sin alimentar, el LNA está apagado y su respuesta no es la de operación.

### 9.3 Cómo se conecta con el GPS
La desadaptación pierde potencia de señal. Esa pérdida baja la C/N0 del receptor:

```
pérdida por desadaptación (dB) = −10·log10(1 − |Γ|²)
```
Con |Γ| = 0.316 (−10 dB): ≈ 0.46 dB. Ese valor se puede aplicar al simulador mediante `cn0_offset_db` de cada receptor, para estudiar cómo una unidad peor adaptada podría rastrear peor los satélites y cambiar el conjunto que usa (lo que a su vez afecta al diferencial).

---

## 10. El simulador

Sirve para probar el software sin hardware. Importante: **no inventa coordenadas**; genera pseudorangos y calcula la posición de cada receptor como lo haría un receptor real, y solo entonces escribe NMEA. Pasos del modelo:

1. **Constelación sintética** de 30 satélites en órbita (o almanaque Yuma real).
2. **Geometría**: tiempo de vuelo de la señal y corrección de **Sagnac** (la Tierra gira mientras la señal viaja).
3. **Errores comunes** a ambos receptores: efemérides/reloj (proceso de **Gauss-Markov**, es decir, error que varía lento y con memoria), ionosfera y troposfera residuales (con factor de oblicuidad según la elevación).
4. **Errores independientes**: multitrayecto dependiente de la elevación, ruido dependiente de C/N0, reloj del receptor.
5. **Selección de satélites** con máscara de elevación y umbral de C/N0, lo que reproduce de forma natural el "distinto conjunto de satélites".
6. **Posición** por mínimos cuadrados ponderados y DOP reales.
7. **NMEA** con cuantización de 4 decimales de minuto.

En simulación la **verdad de terreno es exacta** y se guarda en `meta.json`; en datos reales no existe. Los parámetros por defecto son plausibles pero **no están calibrados con el Mighty Mouse**: con logs reales hay que ajustarlos hasta reproducir las estadísticas observadas. Además, un receptor real filtra la posición y aplica sus propios modelos atmosféricos, lo que el simulador solo aproxima.

---

## 11. Glosario

| Término | Significado |
| --- | --- |
| **Bias-tee** | Dispositivo que inyecta DC al coaxial sin pasar por el VNA |
| **C/N0** | Relación portadora/densidad de ruido (dB-Hz) |
| **CEP50 / CEP95** | Radio del círculo que contiene el 50 % / 95 % de las posiciones |
| **DGPS** | GPS diferencial |
| **DOP (HDOP, VDOP, PDOP)** | Factor de degradación geométrica de la precisión |
| **2DRMS** | Dos veces la distancia RMS horizontal |
| **ECEF** | Coordenadas cartesianas fijas a la Tierra |
| **ENU** | Coordenadas locales Este-Norte-Arriba |
| **Época** | Una solución de posición en un instante (típico 1 por segundo) |
| **Fix** | Solución de posición válida |
| **Geoide** | Superficie equipotencial que aproxima el nivel medio del mar |
| **Gauss-Markov** | Proceso aleatorio con memoria, útil para errores lentos |
| **GGA / GSA / GSV / RMC** | Sentencias NMEA (ver §4) |
| **Γ (gamma)** | Coeficiente de reflexión |
| **LNA** | Amplificador de bajo ruido |
| **Línea base** | Distancia entre referencia y móvil |
| **NMEA 0183** | Protocolo de texto de los receptores GNSS |
| **Pseudorango** | Distancia aparente medida por el receptor, con error de reloj |
| **S11** | Parámetro de reflexión de un puerto (aquí, la antena) |
| **Skyplot** | Mapa polar de los satélites en el cielo |
| **SOL** | Calibración Short-Open-Load |
| **Touchstone** | Formato de texto `.sNp` de parámetros S |
| **UERE** | Error equivalente del pseudorango para el usuario |
| **VNA** | Analizador vectorial de redes |
| **VSWR** | Relación de onda estacionaria de voltaje |
| **WGS-84** | Sistema geodésico de referencia usado por GPS |

---

### Lecturas recomendadas
- Misra y Enge, *Global Positioning System: Signals, Measurements, and Performance*.
- Kaplan y Hegarty, *Understanding GPS/GNSS: Principles and Applications*.
- Pozar, *Microwave Engineering* (parámetros S, carta de Smith, adaptación).
- Balanis, *Antenna Theory* (antenas microstrip).
- Documentación de NMEA 0183 y del formato Touchstone (IBIS Open Forum).
- Efron y Tibshirani, *An Introduction to the Bootstrap*; Politis y Romano sobre bootstrap de bloques estacionario.
