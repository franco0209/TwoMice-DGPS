"""Etapas de validación del SDR (USRP / RTL-SDR). Solo RECEPCIÓN: nunca se transmite.

Cada función ejecuta una herramienta externa con `subprocess` (sin shell, con
timeout y argumentos validados), parsea la salida y devuelve
`{ok, stage, message, ...}`, igual que `acquisition.probe_port`.

Para poder probar sin hardware, todas aceptan `runner`: un callable
`runner(argv, timeout) -> (returncode, texto)` que sustituye a subprocess.
"""
from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from typing import Callable

import numpy as np

L1_HZ = 1_575.42e6
TOOLS = {
    "uhd_find_devices": ["uhd_find_devices", "--version"],
    "uhd_usrp_probe": None,
    "rtl_test": None,
    "rtl_biast": None,
    "gnss-sdr": ["gnss-sdr", "--version"],
}

Runner = Callable[[list[str], float], tuple[int, str]]


def _run(argv: list[str], timeout: float) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=False)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{argv[0]}: no está instalado"
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"") if isinstance(e.stderr, bytes) else (e.stderr or "")
        if isinstance(out, bytes):
            out = out.decode(errors="ignore")
        if isinstance(err, bytes):
            err = err.decode(errors="ignore")
        return 124, out + err


# ------------------------------------------------------------ validación de args

_IP_OR_HOST = re.compile(r"^[A-Za-z0-9.\-]{1,253}$")
_SERIAL = re.compile(r"^[A-Za-z0-9]{1,32}$")
_TYPES = {"b200", "b210", "b205mini", "x300", "x310", "n200", "n210", "usrp2", "e310"}


def valid_ip(ip: str) -> str:
    """Devuelve la IP normalizada o lanza ValueError (impide inyectar flags/args)."""
    return str(ipaddress.ip_address(ip.strip()))


def device_args(args: str) -> list[str]:
    """Valida una cadena de device args de UHD ('addr=192.168.10.2', 'serial=ABC', 'type=b200').

    Solo se permiten las claves addr, serial, type, name y second_addr; sin espacios
    ni caracteres de shell. Devuelve [] si está vacía.
    """
    args = (args or "").strip()
    if not args:
        return []
    pairs = []
    for part in args.split(","):
        if "=" not in part:
            raise ValueError(f"Argumento de dispositivo inválido: {part!r}")
        k, v = (s.strip() for s in part.split("=", 1))
        if k not in {"addr", "serial", "type", "name", "second_addr"}:
            raise ValueError(f"Clave de dispositivo no permitida: {k!r}")
        if k in ("addr", "second_addr"):
            if not _IP_OR_HOST.match(v):
                raise ValueError(f"Dirección inválida: {v!r}")
        elif k == "type":
            if v.lower() not in _TYPES:
                raise ValueError(f"Tipo de USRP desconocido: {v!r}")
        elif not _SERIAL.match(v):
            raise ValueError(f"Valor inválido para {k}: {v!r}")
        pairs.append(f"{k}={v}")
    return [f"--args={','.join(pairs)}"]


def _base(stage: str, **kw) -> dict:
    return {"ok": False, "stage": stage, "message": "", **kw}


# ------------------------------------------------------------------ 1. herramientas


def tools_status(*, which=shutil.which, runner: Runner = _run) -> dict:
    """¿Están instaladas las herramientas? Incluye versión cuando se puede obtener."""
    out = {}
    for name in TOOLS:
        path = which(name)
        entry = {"installed": bool(path), "path": path, "version": None}
        if path:
            if name == "uhd_find_devices":
                _, txt = runner(["uhd_config_info", "--version"], 8)
                m = re.search(r"UHD[_ ]?(\d+\.\d+\.\d+(?:\.\d+)?)", txt)
                entry["version"] = m.group(1) if m else None
            elif name == "gnss-sdr":
                _, txt = runner([name, "--version"], 8)
                m = re.search(r"gnss-sdr\s+version\s+(\S+)", txt, re.I) or re.search(r"(\d+\.\d+(?:\.\d+)?)", txt)
                entry["version"] = m.group(1) if m else None
        out[name] = entry
    needs = {"usrp": ["uhd_find_devices", "uhd_usrp_probe"], "rtlsdr": ["rtl_test"], "gnsssdr": ["gnss-sdr"]}
    ready = {k: all(out[t]["installed"] for t in v) for k, v in needs.items()}
    hints = []
    if not ready["usrp"]:
        hints.append("USRP: instale UHD (sudo apt install uhd-host libuhd-dev) y las imágenes FPGA con uhd_images_downloader.")
    if not ready["rtlsdr"]:
        hints.append("RTL-SDR: sudo apt install rtl-sdr (y reglas udev; reinicie la sesión).")
    if not ready["gnsssdr"]:
        hints.append("GNSS-SDR: sudo apt install gnss-sdr (o compile desde https://gnss-sdr.org).")
    return {"tools": out, "ready": ready, "hints": hints}


# ------------------------------------------------------------------ 2. conectar


def ping(ip: str, count: int = 3, *, runner: Runner = _run) -> dict:
    """Ping al USRP por Ethernet. `ok` si responde al menos un paquete."""
    try:
        ip = valid_ip(ip)
    except ValueError:
        return _base("ping", ip=ip, message=f"IP inválida: {ip!r}")
    count = max(1, min(int(count), 10))
    rc, txt = runner(["ping", "-c", str(count), "-W", "2", ip], 2 * count + 5)
    if rc == 127:
        return _base("ping", ip=ip, message="No se encontró el comando ping.")
    m = re.search(r"(\d+) (?:packets )?received", txt)
    got = int(m.group(1)) if m else 0
    rtt = re.search(r"= [\d.]+/([\d.]+)/", txt)
    out = _base("ping", ip=ip, sent=count, received=got, rtt_ms=float(rtt.group(1)) if rtt else None)
    if got:
        out.update(ok=True, stage="ok", message=f"{got}/{count} respuestas" + (f", RTT medio {out['rtt_ms']} ms" if rtt else ""))
    else:
        out["message"] = ("El USRP no responde. Revise cable, alimentación y que la interfaz de red de la PC "
                          f"esté en la misma subred que {ip} (p. ej. 192.168.10.1/24; MTU 9000 recomendado en 10GbE).")
    return out


def usb_devices(*, runner: Runner = _run) -> dict:
    """Lista USB (lsusb) y marca USRP (Ettus/NI) y RTL-SDR (Realtek 0bda:2832/2838)."""
    rc, txt = runner(["lsusb"], 8)
    if rc == 127:
        return _base("usb", message="No se encontró lsusb (sudo apt install usbutils).", devices=[])
    devs = []
    for line in txt.splitlines():
        m = re.search(r"ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)", line, re.I)
        if not m:
            continue
        vid, pid, name = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        kind = None
        if vid in ("2500", "3923"):
            kind = "usrp"
        elif vid == "0bda" and pid in ("2832", "2838", "2831"):
            kind = "rtlsdr"
        if kind:
            devs.append({"kind": kind, "vid": vid, "pid": pid, "name": name})
    out = _base("usb", devices=devs)
    if devs:
        out.update(ok=True, stage="ok", message=f"{len(devs)} dispositivo(s) SDR por USB")
    else:
        out["message"] = ("No hay USRP ni RTL-SDR en el bus USB. Revise el cable/puerto (USB 3.0 para B2xx) "
                          "y las reglas udev.")
    return out


# ------------------------------------------------------------------ 3. detectar


def parse_find_devices(txt: str) -> list[dict]:
    devs: list[dict] = []
    cur: dict | None = None
    for line in txt.splitlines():
        if re.search(r"-- UHD Device \d+", line):
            cur = {}
            devs.append(cur)
            continue
        m = re.match(r"\s*(\w+):\s*(.*)$", line)
        if cur is not None and m:
            cur[m.group(1)] = m.group(2).strip()
    return devs


def find_devices(args: str = "", *, runner: Runner = _run) -> dict:
    try:
        extra = device_args(args)
    except ValueError as e:
        return _base("find", devices=[], message=str(e))
    rc, txt = runner(["uhd_find_devices", *extra], 30)
    if rc == 127:
        return _base("tools", devices=[], message="uhd_find_devices no está instalado (paquete uhd-host).")
    devs = parse_find_devices(txt)
    out = _base("find", devices=devs)
    if devs:
        out.update(ok=True, stage="ok", message=f"{len(devs)} USRP encontrado(s)")
    elif "No UHD Devices Found" in txt or rc == 0:
        out["message"] = ("UHD no ve ningún USRP. Ethernet: compruebe el ping y la IP; USB: cable/puerto y "
                          "imágenes FPGA (uhd_images_downloader).")
    else:
        out["message"] = f"uhd_find_devices falló: {txt.strip()[-200:]}"
    return out


def parse_rtl_test(txt: str) -> dict:
    """Salida de `rtl_test -t`: lista de dispositivos y tuner."""
    devs = re.findall(r"^\s*(\d+):\s*(.+)$", txt, re.M)
    tuner = re.search(r"Found (\w[\w ]*?) tuner", txt)
    return {
        "devices": [{"index": int(i), "name": n.strip()} for i, n in devs],
        "tuner": tuner.group(1).strip() if tuner else None,
        "no_device": "No supported devices found" in txt,
        "busy": "usb_claim_interface error" in txt or "Failed to open" in txt,
        "permission": "Permission denied" in txt or "usb_open error -3" in txt,
        "kernel_driver": "dvb_usb_rtl28xxu" in txt or "kernel driver" in txt.lower(),
    }


def rtl_find(index: int = 0, *, runner: Runner = _run) -> dict:
    rc, txt = runner(["rtl_test", "-d", str(int(index)), "-t"], 12)
    if rc == 127:
        return _base("tools", devices=[], message="rtl_test no está instalado (sudo apt install rtl-sdr).")
    p = parse_rtl_test(txt)
    out = _base("find", index=int(index), **p)
    if p["no_device"]:
        out["message"] = "No hay ningún RTL-SDR conectado."
    elif p["permission"]:
        out["message"] = "Sin permisos USB: instale las reglas udev de rtl-sdr y reconecte el dongle."
    elif p["busy"] or p["kernel_driver"]:
        out["message"] = ("El dongle está ocupado o lo reclama el driver DVB del kernel: "
                          "añada «blacklist dvb_usb_rtl28xxu» en /etc/modprobe.d y reconecte.")
    elif p["devices"] and p["tuner"]:
        out.update(ok=True, stage="ok", message=f"{p['devices'][0]['name']} · tuner {p['tuner']}")
    else:
        out["message"] = f"Salida de rtl_test no reconocida: {txt.strip()[-200:]}"
    return out


# ------------------------------------------------------------------ 4. sondear


def parse_usrp_probe(txt: str) -> dict:
    def g(pat):
        m = re.search(pat, txt, re.I | re.M)
        return m.group(1).strip() if m else None

    gain = re.search(r"RX Frontend:[\s\S]*?Gain range PGA:\s*([\d.\-]+)\s*to\s*([\d.\-]+)", txt)
    if not gain:
        gain = re.search(r"Gain range \w+:\s*([\d.\-]+)\s*to\s*([\d.\-]+)\s*dB", txt)
    freq = re.search(r"RX (?:Frontend|Dboard)[\s\S]*?Freq range:\s*([\d.]+)\s*to\s*([\d.]+)\s*MHz", txt)
    return {
        "product": g(r"^\s*\|?\s*Product:\s*(.+)$") or g(r"Product:\s*(.+)"),
        "serial": g(r"Serial:\s*(\w+)"),
        "rx_channels": len(re.findall(r"RX Channel:\s*\d+", txt)) or len(re.findall(r"RX Dboard", txt)),
        "gain_db": [float(gain.group(1)), float(gain.group(2))] if gain else None,
        "freq_mhz": [float(freq.group(1)), float(freq.group(2))] if freq else None,
    }


def probe_usrp(args: str = "", *, runner: Runner = _run) -> dict:
    try:
        extra = device_args(args)
    except ValueError as e:
        return _base("probe", message=str(e))
    rc, txt = runner(["uhd_usrp_probe", *extra], 60)
    if rc == 127:
        return _base("tools", message="uhd_usrp_probe no está instalado (paquete uhd-host).")
    info = parse_usrp_probe(txt)
    out = _base("probe", **info)
    if rc != 0 or not (info["product"] or info["serial"]):
        out["message"] = f"No se pudo sondear el USRP: {txt.strip()[-250:] or 'sin salida'}"
        return out
    in_band = info["freq_mhz"] is None or info["freq_mhz"][0] <= L1_HZ / 1e6 <= info["freq_mhz"][1]
    if not in_band:
        out["message"] = (f"El front-end ({info['freq_mhz'][0]}–{info['freq_mhz'][1]} MHz) no cubre GPS L1 "
                          "(1575.42 MHz). Use otra daughterboard.")
        return out
    out.update(ok=True, stage="ok", message=f"{info['product'] or 'USRP'} · {info['rx_channels']} canal(es) RX")
    return out


# ------------------------------------------------------------ 5. bias-tee


def set_biast(index: int, on: bool, *, runner: Runner = _run) -> dict:
    """Activa/desactiva el bias-tee de un RTL-SDR (rtl_biast; requiere el fork con soporte)."""
    rc, txt = runner(["rtl_biast", "-d", str(int(index)), "-b", "1" if on else "0"], 10)
    if rc == 127:
        return _base("biast", message="rtl_biast no está instalado (https://github.com/rtlsdrblog/rtl_biast).")
    ok = rc == 0 and "error" not in txt.lower()
    return _base("ok" if ok else "biast", ok=ok, on=on,
                 message=("Bias-tee " + ("activado" if on else "desactivado")) if ok else txt.strip()[-200:])


# ------------------------------------------------------------ 6. captura de prueba


def iq_metrics(iq: np.ndarray, fs: float, *, full_scale: float = 1.0, nfft: int = 2048) -> dict:
    """Métricas de una captura IQ (complejo, normalizado a ±full_scale).

    - power_dbfs: potencia media respecto a plena escala.
    - clip_pct: % de muestras en ≥ 99 % de plena escala (saturación).
    - dc_offset: |media| relativa al RMS (un DC grande indica LO leakage).
    - snr_db: pico espectral (sobre el piso mediano) para decidir «¿hay señal?».
    - spectrum: espectro Welch reducido (Hz relativos al centro, dB) para graficar.
    """
    iq = np.asarray(iq, dtype=np.complex64) / full_scale
    n = len(iq)
    if n < nfft:
        raise ValueError("Captura demasiado corta")
    p = float(np.mean(np.abs(iq) ** 2))
    rms = np.sqrt(p) or 1e-12
    clip = float(np.mean((np.abs(iq.real) >= 0.99) | (np.abs(iq.imag) >= 0.99)) * 100)
    dc = float(abs(np.mean(iq)) / rms)
    segs = n // nfft
    win = np.hanning(nfft)
    psd = np.zeros(nfft)
    for k in range(segs):
        psd += np.abs(np.fft.fftshift(np.fft.fft(iq[k * nfft:(k + 1) * nfft] * win))) ** 2
    psd /= segs * np.sum(win**2) * fs
    psd_db = 10 * np.log10(psd + 1e-20)
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    # el DC (±3 bins) se excluye del cálculo del piso y del pico
    mask = np.abs(np.arange(nfft) - nfft // 2) > 3
    floor = float(np.median(psd_db[mask]))
    peak = float(np.max(psd_db[mask]))
    step = max(1, nfft // 256)
    return {
        "samples": n, "fs": fs,
        "power_dbfs": float(10 * np.log10(p + 1e-20)),
        "clip_pct": clip, "dc_offset": dc,
        "noise_floor_db": floor, "peak_over_floor_db": peak - floor,
        "spectrum": {"f_hz": freqs[::step].tolist(), "db": psd_db[::step].tolist()},
    }


def judge_capture(m: dict) -> dict:
    """Interpreta las métricas: devuelve {ok, message, warnings}."""
    warn = []
    ok = True
    if m["clip_pct"] > 1.0:
        ok = False
        warn.append(f"Saturación: {m['clip_pct']:.1f} % de muestras al tope. Baje la ganancia.")
    if m["power_dbfs"] < -60:
        ok = False
        warn.append(f"Nivel muy bajo ({m['power_dbfs']:.0f} dBFS): suba la ganancia o revise antena/bias-tee/cable.")
    if m["dc_offset"] > 0.3:
        warn.append("DC offset alto (normal en RTL-SDR; GNSS-SDR lo corrige).")
    # GPS está ~20 dB bajo el ruido térmico: no se ve como pico. Lo que sí se ve es que
    # el piso suba cuando la antena activa está alimentada y conectada.
    if m["peak_over_floor_db"] > 25:
        warn.append("Hay un tono/interferencia fuerte en la banda (pico > 25 dB sobre el piso).")
    return {"ok": ok, "message": "Captura correcta" if ok else warn[0], "warnings": warn}


def capture_usrp(args: str, fs: float, gain: float, seconds: float, *, runner: Runner = _run,
                 out_path: str) -> tuple[int, str]:
    """Captura IQ con el ejemplo `rx_samples_to_file` de UHD (sc16, solo RX)."""
    extra = device_args(args)
    nsamps = int(fs * seconds)
    return runner(["rx_samples_to_file", *extra, "--freq", str(L1_HZ), "--rate", str(fs),
                   "--gain", str(gain), "--nsamps", str(nsamps), "--type", "short",
                   "--file", out_path], seconds + 20)


def capture_rtl(index: int, fs: float, gain: float, seconds: float, *, runner: Runner = _run,
                out_path: str) -> tuple[int, str]:
    """Captura IQ con `rtl_sdr` (uint8 intercalado)."""
    nsamps = int(fs * seconds)
    return runner(["rtl_sdr", "-d", str(int(index)), "-f", str(int(L1_HZ)), "-s", str(int(fs)),
                   "-g", str(gain), "-n", str(nsamps), out_path], seconds + 20)


def load_iq(path: str, kind: str) -> np.ndarray:
    """Lee un archivo IQ: 'usrp' = int16 intercalado (sc16), 'rtlsdr' = uint8 intercalado."""
    if kind == "usrp":
        raw = np.fromfile(path, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        raw = (np.fromfile(path, dtype=np.uint8).astype(np.float32) - 127.5) / 127.5
    raw = raw[: len(raw) // 2 * 2]
    return raw[0::2] + 1j * raw[1::2]


def capture_check(kind: str, *, args: str = "", index: int = 0, fs: float = 2.048e6,
                  gain: float = 40.0, seconds: float = 2.0, runner: Runner = _run,
                  tmp_dir: str | None = None, keep_path: str | None = None) -> dict:
    """Etapa 6: captura ~2 s a 1575.42 MHz y calcula métricas.

    `kind`: 'usrp' | 'rtlsdr'. Si `keep_path` está dado, el archivo IQ se conserva ahí
    (paso 9 «guardar IQ»); si no, se borra.
    """
    import os
    import tempfile

    if kind not in ("usrp", "rtlsdr"):
        return _base("capture", message=f"Tipo de dispositivo no soportado: {kind!r}")
    if not 0.25e6 <= fs <= 10e6:
        return _base("capture", message="Sample rate fuera de rango (0.25–10 MS/s).")
    if not 0.5 <= seconds <= 10:
        return _base("capture", message="Duración fuera de rango (0.5–10 s).")
    fd, path = tempfile.mkstemp(suffix=".iq", dir=tmp_dir)
    os.close(fd)
    try:
        try:
            if kind == "usrp":
                rc, txt = capture_usrp(args, fs, gain, seconds, runner=runner, out_path=path)
            else:
                rc, txt = capture_rtl(index, fs, gain, seconds, runner=runner, out_path=path)
        except ValueError as e:
            return _base("capture", message=str(e))
        if rc == 127:
            tool = "rx_samples_to_file (uhd-host/libuhd-dev ejemplos)" if kind == "usrp" else "rtl_sdr"
            return _base("tools", message=f"Falta {tool}.")
        if rc != 0 or os.path.getsize(path) == 0:
            return _base("capture", message=f"La captura falló: {txt.strip()[-250:] or 'sin datos'}")
        iq = load_iq(path, kind)
        m = iq_metrics(iq, fs)
        verdict = judge_capture(m)
        out = _base("ok" if verdict["ok"] else "capture", **m, **verdict)
        if keep_path:
            shutil.move(path, keep_path)
            out["iq_file"] = keep_path
            path = ""
        return out
    except ValueError as e:
        return _base("capture", message=str(e))
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
