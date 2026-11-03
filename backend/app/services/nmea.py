"""NMEA 0183: generación (simulador) y parseo/ensamblado de épocas (sim y real).

Interfaz común del proyecto: tanto el modo simulado como el receptor real
producen líneas `$GPGGA...*hh`. `EpochAssembler` las convierte en épocas.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pynmea2

# ----------------------------------------------------------------- escritura


def checksum(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def sentence(body: str) -> str:
    return f"${body}*{checksum(body)}"


def _lat(lat: float, decimals: int) -> tuple[str, str]:
    h = "N" if lat >= 0 else "S"
    a = abs(lat)
    d = int(a)
    return f"{d:02d}{(a - d) * 60:0{3 + decimals}.{decimals}f}", h


def _lon(lon: float, decimals: int) -> tuple[str, str]:
    h = "E" if lon >= 0 else "W"
    a = abs(lon)
    d = int(a)
    return f"{d:03d}{(a - d) * 60:0{3 + decimals}.{decimals}f}", h


def _hms(t: dt.datetime) -> str:
    return f"{t:%H%M%S}.{t.microsecond // 10000:02d}"


def gga(t, lat, lon, alt_msl, quality, nsat, hdop, geoid_sep=0.0, decimals=4) -> str:
    if quality == 0:
        return sentence(f"GPGGA,{_hms(t)},,,,,0,00,99.99,,M,,M,,")
    la, lh = _lat(lat, decimals)
    lo, oh = _lon(lon, decimals)
    return sentence(
        f"GPGGA,{_hms(t)},{la},{lh},{lo},{oh},{quality},{nsat:02d},{hdop:.1f},"
        f"{alt_msl:.1f},M,{geoid_sep:.1f},M,,"
    )


def rmc(t, lat, lon, speed_kn, course, valid, decimals=4) -> str:
    date = f"{t:%d%m%y}"
    if not valid:
        return sentence(f"GPRMC,{_hms(t)},V,,,,,,,{date},,,N")
    la, lh = _lat(lat, decimals)
    lo, oh = _lon(lon, decimals)
    return sentence(f"GPRMC,{_hms(t)},A,{la},{lh},{lo},{oh},{speed_kn:.2f},{course:.1f},{date},,,A")


def gsa(fix_type, prns, pdop, hdop, vdop) -> str:
    slots = [f"{p:02d}" for p in prns[:12]] + [""] * (12 - len(prns[:12]))
    if fix_type == 1:
        return sentence(f"GPGSA,A,1,{','.join(slots)},,,")
    return sentence(f"GPGSA,A,{fix_type},{','.join(slots)},{pdop:.1f},{hdop:.1f},{vdop:.1f}")


def gsv(in_view: list[tuple[int, float, float, float | None]]) -> list[str]:
    """in_view: [(prn, elev, azim, snr|None)]. Hasta 4 satélites por sentencia."""
    total = max(1, -(-len(in_view) // 4))
    out = []
    for i in range(total):
        chunk = in_view[i * 4:(i + 1) * 4]
        fields = ""
        for prn, el, az, snr in chunk:
            s = "" if snr is None else f"{round(snr):02d}"
            fields += f",{prn:02d},{round(el):02d},{round(az) % 360:03d},{s}"
        out.append(sentence(f"GPGSV,{total},{i + 1},{len(in_view):02d}{fields}"))
    return out


# ------------------------------------------------------------------- lectura


@dataclass
class SatInfo:
    id: str
    el: float | None
    az: float | None
    snr: float | None


@dataclass
class Epoch:
    utc: dt.datetime | None = None
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    geoid_sep: float | None = None
    quality: int = 0
    nsats: int = 0
    hdop: float | None = None
    pdop: float | None = None
    vdop: float | None = None
    fix_type: int | None = None
    sats_used: list[str] = field(default_factory=list)
    sats_view: list[SatInfo] = field(default_factory=list)
    speed_kn: float | None = None
    course: float | None = None
    valid: bool = False

    def to_dict(self) -> dict:
        return {
            "utc": self.utc.isoformat() if self.utc else None,
            "lat": self.lat, "lon": self.lon, "alt": self.alt,
            "geoid_sep": self.geoid_sep, "quality": self.quality, "nsats": self.nsats,
            "hdop": self.hdop, "pdop": self.pdop, "vdop": self.vdop,
            "fix_type": self.fix_type, "sats_used": self.sats_used,
            "sats_view": [vars(s) for s in self.sats_view],
            "speed_kn": self.speed_kn, "course": self.course, "valid": self.valid,
        }


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


class EpochAssembler:
    """Agrupa sentencias en épocas. Una época nueva empieza cuando se repite
    un tipo de ciclo (GGA, RMC o GSA); GSV se acumula por talker.

    Funciona si la primera sentencia con hora de cada ciclo (GGA o RMC) llega
    antes que las de GSA/GSV del mismo ciclo, que es lo habitual.
    """

    def __init__(self):
        self.bad_lines = 0
        self.good_lines = 0
        self._reset()

    def _reset(self):
        self._seen: set[str] = set()
        self._ep = Epoch()
        self._gsv: dict[str, list[SatInfo]] = {}
        self._rmc_time = None
        self._date = getattr(self, "_date", None)

    def feed(self, line: str) -> Epoch | None:
        """Procesa una línea. Devuelve la época anterior si esta línea abre una nueva."""
        line = line.strip()
        if not line.startswith("$"):
            return None
        try:
            msg = pynmea2.parse(line, check=True)
        except pynmea2.ParseError:
            self.bad_lines += 1
            return None
        except Exception:
            self.bad_lines += 1
            return None
        self.good_lines += 1
        kind = msg.sentence_type
        talker = msg.talker
        out = None
        if kind in ("GGA", "RMC", "GSA") and kind in self._seen:
            out = self._close()
        if kind in ("GGA", "RMC", "GSA"):
            self._seen.add(kind)

        if kind == "GGA":
            e = self._ep
            e.quality = int(msg.gps_qual or 0)
            e.nsats = int(msg.num_sats or 0)
            e.hdop = _f(msg.horizontal_dil)
            if e.quality > 0:
                e.lat, e.lon = msg.latitude, msg.longitude
                e.alt = _f(msg.altitude)
                e.geoid_sep = _f(msg.geo_sep)
            self._gga_time = msg.timestamp
        elif kind == "RMC":
            e = self._ep
            e.valid = msg.status == "A"
            e.speed_kn = _f(msg.spd_over_grnd)
            e.course = _f(msg.true_course)
            self._date = msg.datestamp
            self._rmc_time = msg.timestamp
            if self._rmc_time and self._date:
                e.utc = dt.datetime.combine(self._date, self._rmc_time, tzinfo=dt.timezone.utc)
        elif kind == "GSA":
            e = self._ep
            e.fix_type = int(msg.mode_fix_type or 1)
            e.sats_used += [f"{talker}{int(getattr(msg, f'sv_id{i:02d}')):02d}"
                            for i in range(1, 13) if getattr(msg, f"sv_id{i:02d}", "")]
            e.pdop, e.vdop = _f(msg.pdop), _f(msg.vdop)
            if e.hdop is None:
                e.hdop = _f(msg.hdop)
        elif kind == "GSV":
            if int(msg.msg_num) == 1:
                self._gsv[talker] = []
            for i in range(1, 5):
                prn = getattr(msg, f"sv_prn_num_{i}", "")
                if prn:
                    self._gsv.setdefault(talker, []).append(SatInfo(
                        id=f"{talker}{int(prn):02d}",
                        el=_f(getattr(msg, f"elevation_deg_{i}", None)),
                        az=_f(getattr(msg, f"azimuth_{i}", None)),
                        snr=_f(getattr(msg, f"snr_{i}", None)),
                    ))
        return out

    def _close(self) -> Epoch | None:
        e = self._ep
        e.sats_view = [s for lst in self._gsv.values() for s in lst]
        had = bool(self._seen)
        if e.utc is None and self._date and getattr(self, "_gga_time", None):
            e.utc = dt.datetime.combine(self._date, self._gga_time, tzinfo=dt.timezone.utc)
        self._reset()
        return e if had else None

    def flush(self) -> Epoch | None:
        return self._close()
