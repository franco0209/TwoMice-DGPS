# Plan: adquisición con SDR (USRP / RTL-SDR) en Linux

Estado al cierre de la sesión en Windows y trabajo a continuar en Linux.

## 1. Cambio de enfoque

No habrá módulos NMEA. La posición sale de **procesar IQ de GPS L1 (1575.42 MHz)
con un receptor GNSS por software**:

```
antena activa -> SDR (USRP por Ethernet/USB, o RTL-SDR por USB) -> IQ
   -> GNSS-SDR (uno por receptor: ref y móvil) -> NMEA
   -> pipeline existente (ReceiverChannel / EpochAssembler) -> análisis diferencial
```

El análisis (diferencial, métricas, informe) **no cambia**: la interfaz común sigue
siendo NMEA. Solo cambia la *fuente* de las líneas.

Decisiones tomadas por el usuario:
- Procesamiento: **GNSS-SDR**.
- Hardware: **mixto / aún no definido** → el asistente soporta USRP (Ethernet o USB)
  y RTL-SDR, elegible por receptor.
- Sistema: **Linux** (UHD, rtl-sdr y GNSS-SDR se instalan allí).
- Solo **recepción**: nunca transmitir (a diferencia del proyecto de referencia
  Lain5G, que también hace TX; aquí no hay nada de seguridad RF de transmisión).

## 2. Ya hecho (en este commit)

- Asistente guiado de adquisición (`frontend/src/views/AcquisitionView.jsx`):
  pasos con validación que bloquean «Siguiente» hasta pasar. Hoy está pensado para
  receptores NMEA por puerto serie; **hay que adaptar los pasos a SDR** (sección 4).
- `AcquisitionLive.jsx`: KPIs y gráficas en vivo (sin cambios de lógica).
- Backend: `POST /api/gps/probe` + `probe_port()` (sondeo de NMEA en puerto serie),
  con test. Se conserva como fuente opcional (receptor NMEA real).
- `MANUAL.md` sección 3 actualizada al asistente.

## 3. Lo que NO se sabe aún (verificar en Linux)

El repo Lain5G (`guallycanazas/Lain5G`) se revisó solo a nivel de README/docs: no
muestra comandos de conexión a los USRP (ping, `uhd_find_devices`, IP, MTU). Los
detalles están en `deployments/4g-volte/x310/` y `src/backend/` (no leídos).
**Pendiente:** leer esas rutas para copiar sus valores reales (IP del USRP del
lab, device args, MTU) en vez de suponerlos.

Nada de SDR se ha probado: en la PC Windows no había UHD, rtl-sdr ni GNSS-SDR.

## 4. Pasos nuevos del asistente (por receptor: ref y móvil)

Origen del receptor: `USRP-Ethernet` · `USRP-USB` · `RTL-SDR` · `Archivo IQ/NMEA` ·
`Simulación` (se mantiene).

| # | Etapa | Qué indica al usuario | Validación (backend) |
|---|-------|-----------------------|----------------------|
| 1 | Herramientas | Instalar UHD / rtl-sdr / GNSS-SDR | `which uhd_find_devices rtl_test gnss-sdr` y versiones |
| 2 | Conectar | Cablear USRP (Ethernet 10GbE/1GbE) o USB, alimentar | USRP-Eth: IP configurada → **`ping -c 3 <ip>`**; USB: `lsusb`/reglas udev |
| 3 | Detectar | — | USRP: `uhd_find_devices [--args addr=<ip>]`; RTL-SDR: `rtl_test -t` |
| 4 | Sondear | — | USRP: `uhd_usrp_probe` (modelo, canales, rango de ganancia/frecuencia); RTL-SDR: lista de dispositivos y tuner |
| 5 | Antena y bias-tee | Antena activa necesita alimentación (3–5 V). RTL-SDR: bias-tee del dongle si lo tiene (`rtl_biast`); USRP: bias-tee externo/ver modelo. **Aviso: no conectar DC a un puerto sin bloqueo** | Confirmación explícita del usuario (no medible) |
| 6 | Captura de prueba | Antena a cielo abierto | Capturar ~2 s a 1575.42 MHz, fs 2.048–4 MS/s: potencia, saturación (clipping), DC offset, espectro; «¿hay señal?» por comparación de piso de ruido |
| 7 | Adquisición GNSS | Esperar | Lanzar GNSS-SDR; seguir su salida: satélites adquiridos, tracking, C/N0; fix cuando haya PVT |
| 8 | Registrar | No mover antenas | Épocas de ambos receptores (igual que hoy) |
| 9 | Cierre | — | Sesión guardada + guardar IQ opcional |

Parámetros típicos a exponer: frecuencia (1575.42 MHz fija), sample rate,
ganancia, serial/IP del dispositivo, ref vs rover, duración.

### Dos receptores
- **2 SDR independientes** (caso más probable): un proceso GNSS-SDR por SDR.
- **1 USRP con 2 canales RX** (B210 / X310 con 2 daughterboards): un solo reloj →
  más simple y mejor para diferencial; un GNSS-SDR por canal (o una entrada
  multicanal). Decidir según el hardware real.
- RTL-SDR: un solo canal por dongle; para ref+móvil se necesitan dos dongles.
  Ojo con su TCXO/ppm; GNSS-SDR lo compensa pero limita la calidad.

## 5. Backend a construir (Linux)

- `services/sdr.py`
  - `tools_status()`: presencia/versión de `uhd_find_devices`, `rtl_test`, `gnss-sdr`.
  - `ping(ip)`, `find_devices(args)`, `probe_usrp(args)`, `probe_rtlsdr(index)`:
    ejecutan los comandos con `subprocess` (timeout, sin shell, args validados),
    parsean la salida y devuelven `{ok, stage, message, ...}` como `probe_port`.
  - `capture_check(device, fs, gain)`: captura corta → métricas (numpy).
- `services/gnsssdr.py`
  - Generar el `.conf` de GNSS-SDR a partir de parámetros (`SignalSource`:
    `UHD_Signal_Source` / `Osmosdr_Signal_Source` o `File_Signal_Source`;
    PVT con `flag_nmea_tty_port` o `nmea_dump_filename`).
  - Lanzar/parar el proceso y **alimentar `ReceiverChannel.ingest()`** con las
    líneas NMEA (tail del archivo o pty/UDP). Mismo destino que `serial_reader`.
  - Extraer de la salida de GNSS-SDR el estado de adquisición/tracking para el asistente.
- `routers/sdr.py`: endpoints de cada etapa (`/api/sdr/tools`, `/ping`, `/find`,
  `/probe`, `/capture-check`, `/gnsssdr/start|stop|status`).
- Integrar como nueva fuente en `AcquisitionSession` (`start_sdr`), junto a
  `start_sim`, `start_real`, `start_replay`.
- Tests con *fakes* de subprocess (igual que `probe_port` con `opener`) y, si
  se puede, GNSS-SDR sobre un archivo IQ de ejemplo.

## 6. Frontend a construir

- Reemplazar los pasos «Conectar/Validar NMEA/Esperar fix» por los de la sección 4,
  con selector de tipo de dispositivo por receptor.
- Mostrar espectro/potencia de la captura de prueba (Plotly, ya en el proyecto) y
  el progreso de adquisición GNSS-SDR (satélites buscados/adquiridos/trackeados).
- Mantener Simulación y la ruta NMEA serie como opciones de origen.

## 7. Orden de trabajo sugerido en Linux

1. Instalar: `uhd` (+ imágenes FPGA con `uhd_images_downloader`), `rtl-sdr`
   (+ reglas udev), `gnss-sdr`. Registrar versiones.
2. Con el hardware real, ejecutar a mano la cadena (ping → `uhd_find_devices` →
   `uhd_usrp_probe` / `rtl_test`) y anotar salidas reales para escribir los parsers.
3. Capturar IQ a archivo y correr GNSS-SDR sobre él para obtener NMEA; validar
   contra el simulador/verdad conocida.
4. Implementar `services/sdr.py` + tests → `gnsssdr.py` → router → asistente.
5. Prueba extremo a extremo con dos receptores; actualizar README/MANUAL/TEORIA
   (la teoría de NMEA vs. IQ cambia: el diferencial sigue en el dominio de la posición).

## 8. Notas

- RF: solo recepción. Antena activa → cuidar la polarización DC (bias-tee/bloqueador).
- GPS L1 C/A en interiores/ciudad es débil; buscar cielo abierto. Considerar el
  tiempo de arranque en frío de GNSS-SDR (puede tardar minutos).
- Los parámetros del simulador siguen sin calibrar con el equipo real.
