"""Exportación de resultados: CSV y informe PDF (matplotlib, sin dependencias extra)."""
from __future__ import annotations

import csv
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

BLUE, ORANGE = "#2563eb", "#f59e0b"


def series_csv(res: dict) -> str:
    s = res["series"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["t_s", "antes_e_m", "antes_n_m", "antes_u_m", "despues_e_m", "despues_n_m", "despues_u_m"])
    for t, b, a in zip(s["t_s"], s["before"], s["after"]):
        w.writerow([t, *b, *a])
    return buf.getvalue()


def _fmt(v, d=2):
    return "—" if v is None else f"{v:.{d}f}"


def _ci(res, key):
    c = res["bootstrap"].get("ci", {}).get(key)
    return f"[{c[0]:.2f}, {c[1]:.2f}]" if c else "—"


def _circle(ax, r, color, label, ls="-"):
    th = np.linspace(0, 2 * np.pi, 200)
    ax.plot(r * np.cos(th), r * np.sin(th), color=color, ls=ls, lw=1.2, label=label)


def build_pdf(res: dict, title: str, meta: dict | None = None, vna: dict | None = None) -> bytes:
    buf = io.BytesIO()
    b, a, ep, bl = res["before"], res["after"], res["epochs"], res["baseline"]
    err_b = np.array(res["series"]["before"])
    err_a = np.array(res["series"]["after"])
    t = np.array(res["series"]["t_s"]) / 60.0
    with PdfPages(buf) as pdf:
        # ---- Página 1: resumen
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.08, 0.95, title, fontsize=16, weight="bold")
        fig.text(0.08, 0.93, "Diferencial en dominio de posición · Mighty Mouse 3GPS (referencia + móvil)",
                 fontsize=9, color="#555")
        y = 0.89
        info = [
            f"Posición de referencia (lat, lon, h): {res['ref_known'][0]:.6f}, {res['ref_known'][1]:.6f}, {res['ref_known'][2]:.1f} m",
            "Verdad del móvil: " + ("conocida (exactitud + precisión)" if res["accuracy"]
                                    else "NO disponible: solo precisión (dispersión respecto a la propia media)"),
            f"Modo de sesión: {(meta or {}).get('mode', 'archivos subidos')}"
            + (" · DATOS SIMULADOS" if (meta or {}).get("mode") == "sim" else ""),
            f"Épocas: {ep['simultaneous']} simultáneas · {ep['same_sats']} con el mismo conjunto de satélites "
            f"({ep['same_sats_pct']:.0f} %) · {ep['discarded']} descartadas",
            f"Bootstrap por bloques: bloque = {res['bootstrap']['block']} épocas, {res['bootstrap']['n_boot']} remuestreos, IC 95 %",
        ]
        for line in info:
            fig.text(0.08, y, line, fontsize=8.5)
            y -= 0.022
        y -= 0.015
        rows = [("RMSE horizontal (m)", "rmse_h"), ("CEP50 (m)", "cep50"), ("CEP95 (m)", "cep95"),
                ("2DRMS (m)", "2drms"), ("RMSE vertical (m)", "rmse_v"), ("Sesgo horizontal (m)", "bias_h")]
        ci_keys = {"rmse_h": "rmse_h", "cep50": "cep50", "cep95": "cep95", "2drms": "2drms"}
        ax = fig.add_axes([0.08, y - 0.30, 0.84, 0.30])
        ax.axis("off")
        cells = []
        for lbl, k in rows:
            imp = res["improvement"].get(k)
            cells.append([lbl, _fmt(b.get(k)), _fmt(a.get(k)),
                          "—" if imp is None else f"{imp:.0f} %",
                          _ci(res, f"imp_{ci_keys[k]}") if k in ci_keys else "—"])
        tb = ax.table(cellText=cells, colLabels=["Métrica", "1 receptor", "Diferencial", "Mejora", "IC 95 % mejora (%)"],
                      loc="upper center", cellLoc="center")
        tb.auto_set_font_size(False)
        tb.set_fontsize(8.5)
        tb.scale(1, 1.5)
        y -= 0.33
        fig.text(0.08, y, "Línea base ref → móvil", fontsize=11, weight="bold")
        y -= 0.025
        lines = [f"Medida con 1 receptor (móvil medido − ref conocida): {bl['raw_len_mean']:.2f} ± {bl['raw_len_std']:.2f} m",
                 f"Medida diferencial (móvil − ref, ambos medidos): {bl['dgps_len_mean']:.2f} ± {bl['dgps_len_std']:.2f} m"]
        if "true_len" in bl:
            lines += [f"Longitud verdadera: {bl['true_len']:.2f} m · error RMS: 1 receptor "
                      f"{bl['raw_len_err_rmse']:.2f} m, diferencial {bl['dgps_len_err_rmse']:.2f} m"]
        for line in lines:
            fig.text(0.08, y, line, fontsize=8.5)
            y -= 0.022
        y -= 0.015
        fig.text(0.08, y, "Lectura", fontsize=11, weight="bold")
        y -= 0.025
        notes = [
            "El diferencial en dominio de posición solo cancela errores comunes (efemérides, reloj, iono/tropo).",
            "El multitrayecto y el ruido de cada receptor no se cancelan y pueden aumentar levemente la dispersión.",
            f"Autocorrelación lag-1 del error horizontal: antes {res['stability']['lag1_before']:.2f}, "
            f"después {res['stability']['lag1_after']:.2f} (por eso se usa bootstrap por bloques).",
            "Sin verdad del móvil, el sesgo común no es medible y las cifras describen precisión, no exactitud."
            if not res["accuracy"] else "Con verdad del móvil, las cifras incluyen el sesgo (exactitud).",
        ]
        for line in notes:
            fig.text(0.08, y, "• " + line, fontsize=8.5)
            y -= 0.022
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Página 2: dispersión, histograma, series
        fig, axs = plt.subplots(2, 2, figsize=(8.27, 11.69))
        ax = axs[0, 0]
        ax.scatter(err_b[:, 0], err_b[:, 1], s=4, c=ORANGE, alpha=.5, label="1 receptor")
        ax.scatter(err_a[:, 0], err_a[:, 1], s=4, c=BLUE, alpha=.5, label="Diferencial")
        _circle(ax, b["cep50"], ORANGE, "CEP50 1 rx", "--")
        _circle(ax, a["cep50"], BLUE, "CEP50 DGPS", "--")
        _circle(ax, b["cep95"], ORANGE, "CEP95 1 rx")
        _circle(ax, a["cep95"], BLUE, "CEP95 DGPS")
        ax.axhline(0, c="#999", lw=.5)
        ax.axvline(0, c="#999", lw=.5)
        ax.set_aspect("equal")
        ax.set_xlabel("Este (m)")
        ax.set_ylabel("Norte (m)")
        ax.set_title("Dispersión horizontal", fontsize=10)
        ax.legend(fontsize=6)
        ax = axs[0, 1]
        rb, ra = np.hypot(err_b[:, 0], err_b[:, 1]), np.hypot(err_a[:, 0], err_a[:, 1])
        bins = np.linspace(0, max(rb.max(), ra.max()), 30)
        ax.hist(rb, bins, color=ORANGE, alpha=.6, label="1 receptor")
        ax.hist(ra, bins, color=BLUE, alpha=.6, label="Diferencial")
        ax.set_xlabel("Error horizontal (m)")
        ax.set_title("Histograma del error", fontsize=10)
        ax.legend(fontsize=7)
        for ax, i, lbl in ((axs[1, 0], 0, "Este"), (axs[1, 1], 1, "Norte")):
            ax.plot(t, err_b[:, i], c=ORANGE, lw=.6, label="1 receptor")
            ax.plot(t, err_a[:, i], c=BLUE, lw=.6, label="Diferencial")
            ax.set_xlabel("Tiempo (min)")
            ax.set_ylabel("Error (m)")
            ax.set_title(f"Error {lbl}", fontsize=10)
            ax.legend(fontsize=7)
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Página 3: antena (opcional)
        if vna:
            fig, axs = plt.subplots(2, 1, figsize=(8.27, 11.69 / 2))
            axs[0].plot(vna["freq_mhz"], vna["s11_db"], c=BLUE)
            axs[0].axhline(-10, c="#c00", ls=":", lw=.8)
            axs[0].axvline(1575.42, c="#777", ls="--", lw=.8)
            axs[0].set_ylabel("S11 (dB)")
            axs[0].set_title("Antena: S11 (línea punteada: −10 dB; vertical: L1 1575.42 MHz)", fontsize=10)
            axs[1].plot(vna["freq_mhz"], vna["vswr"], c=ORANGE)
            axs[1].set_ylim(1, 5)
            axs[1].set_ylabel("VSWR")
            axs[1].set_xlabel("Frecuencia (MHz)")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
    return buf.getvalue()
