"""Live link to a Bambu Lab X1C over the LAN.

* MQTT over TLS on port 8883, user `bblp`, password = printer access code,
  topic `device/<serial>/report`. We send `pushall` on connect and merge the
  (possibly partial) `print` payloads into one state dict.
* Implicit FTPS on port 990 (same credentials) to fetch the sliced
  `.gcode.3mf` so we can read per-filament usage.

Note for X1 series firmware >= 01.08.x: "Developer Mode" (Settings > Network
on the printer) must be enabled for third-party LAN MQTT / FTP access.
"""
from __future__ import annotations

import asyncio
import ftplib
import io
import json
import logging
import ssl
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from .base import AmsSnapshot, EventHandler, PrintStatus, PrinterStatus, TrayState

log = logging.getLogger("printer.bambu")
ZERO_UUID = "0" * 32


def _deep_merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_ams(print_state: dict) -> AmsSnapshot | None:
    """Build an AmsSnapshot for the first AMS unit from a merged `print` dict."""
    ams_root = print_state.get("ams")
    if not isinstance(ams_root, dict):
        return None
    units = ams_root.get("ams")
    if not isinstance(units, list) or not units:
        return None
    unit = units[0]
    trays_by_idx: dict[int, TrayState] = {i: TrayState(i, False) for i in range(4)}
    for t in unit.get("tray", []) or []:
        idx = _int(t.get("id"))
        if idx is None or idx not in trays_by_idx:
            continue
        ttype = (t.get("tray_type") or "").strip()
        present = bool(ttype)
        uuid = (t.get("tray_uuid") or "").strip().upper() or None
        if uuid == ZERO_UUID:
            uuid = None
        tag = (t.get("tag_uid") or "").strip().upper() or None
        if tag and set(tag) == {"0"}:
            tag = None
        trays_by_idx[idx] = TrayState(
            slot_index=idx,
            present=present,
            tray_uuid=uuid if present else None,
            tag_uid=tag if present else None,
            tray_type=ttype or None,
            tray_sub_brands=(t.get("tray_sub_brands") or "").strip() or None,
            tray_color=(t.get("tray_color") or "").strip().upper() or None,
            tray_weight=_float(t.get("tray_weight")),
            remain_pct=_int(t.get("remain")) if present else None,
            nozzle_temp_min=_int(t.get("nozzle_temp_min")),
            nozzle_temp_max=_int(t.get("nozzle_temp_max")),
            tray_info_idx=(t.get("tray_info_idx") or "").strip() or None,
        )
    tray_now = _int(ams_root.get("tray_now"))
    active = tray_now if tray_now is not None and 0 <= tray_now < 4 else None
    return AmsSnapshot(trays=[trays_by_idx[i] for i in range(4)], active_tray=active)


def parse_print(print_state: dict) -> PrintStatus | None:
    state = print_state.get("gcode_state")
    if not state:
        return None
    mapping = print_state.get("ams_mapping")
    if not (isinstance(mapping, list) and all(isinstance(x, int) for x in mapping)):
        mapping = None
    return PrintStatus(
        gcode_state=str(state).upper(),
        subtask_name=print_state.get("subtask_name") or None,
        gcode_file=print_state.get("gcode_file") or None,
        progress_pct=_int(print_state.get("mc_percent"), 0) or 0,
        ams_mapping=mapping,
        layer_num=_int(print_state.get("layer_num")),
        remaining_minutes=_int(print_state.get("mc_remaining_time")),
    )


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS that wraps the control socket immediately (implicit TLS, port 990)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value


def _insecure_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_3mf_sync(host: str, access_code: str, subtask_name: str, gcode_file: str | None, timeout: int = 30) -> bytes | None:
    """Download the .3mf for a job from the printer's /cache (or root) via FTPS."""
    ftp = ImplicitFTP_TLS(context=_insecure_ctx(), timeout=timeout)
    ftp.connect(host, 990)
    ftp.login("bblp", access_code)
    ftp.prot_p()
    try:
        candidates: list[str] = []
        for d in ("/cache", "/"):
            try:
                names = ftp.nlst(d)
            except ftplib.error_perm:
                continue
            for n in names:
                base = n.rsplit("/", 1)[-1]
                stem = base
                for ext in (".gcode.3mf", ".3mf"):
                    if stem.endswith(ext):
                        stem = stem[: -len(ext)]
                if not base.endswith(".3mf"):
                    continue
                if stem == subtask_name or (gcode_file and gcode_file.rsplit("/", 1)[-1].startswith(stem)):
                    candidates.append(n if n.startswith("/") else f"{d.rstrip('/')}/{n}")
        if not candidates:
            log.warning("3mf for %r not found on printer", subtask_name)
            return None
        buf = io.BytesIO()
        ftp.retrbinary(f"RETR {candidates[0]}", buf.write)
        return buf.getvalue()
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


class BambuPrinter:
    def __init__(self, host: str, serial: str, access_code: str):
        self.host, self.serial, self.access_code = host, serial, access_code
        self.status = PrinterStatus(connected=False, mode="live", message="Not connected")
        self._state: dict = {}
        self._client: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._handler: EventHandler | None = None
        self._stop = threading.Event()
        self._last_ams_key: str | None = None
        self._last_print_key: str | None = None

    # ---- lifecycle ----
    async def start(self, loop, handler):
        self._loop, self._handler = loop, handler
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"spooltrackr-{int(time.time())}", protocol=mqtt.MQTTv311)
        c.username_pw_set("bblp", self.access_code)
        c.tls_set_context(_insecure_ctx())
        c.tls_insecure_set(True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(min_delay=2, max_delay=60)
        self._client = c
        try:
            c.connect_async(self.host, 8883, keepalive=30)
            c.loop_start()
        except Exception as e:  # bad host etc.
            self.status.message = f"Connect error: {e}"
            log.error("MQTT connect error: %s", e)

    async def stop(self):
        self._stop.set()
        if self._client:
            try:
                self._client.disconnect()
                self._client.loop_stop()
            except Exception:
                pass
        self.status.connected = False

    async def fetch_3mf(self, subtask_name: str, gcode_file: str | None) -> bytes | None:
        return await asyncio.to_thread(fetch_3mf_sync, self.host, self.access_code, subtask_name, gcode_file)

    # ---- paho callbacks (run on paho thread) ----
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            self.status.connected = False
            self.status.message = f"MQTT refused: {reason_code}"
            log.warning("MQTT connect refused: %s", reason_code)
            return
        self.status.connected = True
        self.status.message = "Connected"
        client.subscribe(f"device/{self.serial}/report")
        client.publish(f"device/{self.serial}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
        client.publish(f"device/{self.serial}/request", json.dumps({"info": {"sequence_id": "0", "command": "get_version"}}))
        log.info("MQTT connected to %s", self.host)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.status.connected = False
        self.status.message = f"Disconnected ({reason_code})"
        log.warning("MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        p = payload.get("print")
        if not isinstance(p, dict):
            return
        _deep_merge(self._state, p)
        self.status.last_message_at = datetime.now(timezone.utc).isoformat()
        self.status.nozzle_temp = _float(self._state.get("nozzle_temper"))
        self.status.bed_temp = _float(self._state.get("bed_temper"))
        self.status.extra = {
            "wifi_signal": self._state.get("wifi_signal"),
            "ams_humidity": (self._state.get("ams", {}).get("ams") or [{}])[0].get("humidity") if isinstance(self._state.get("ams"), dict) else None,
        }
        if "ams" in p:
            snap = parse_ams(self._state)
            if snap:
                key = json.dumps([t.__dict__ for t in snap.trays] + [snap.active_tray], sort_keys=True)
                if key != self._last_ams_key:
                    self._last_ams_key = key
                    self._dispatch("ams", snap)
        if any(k in p for k in ("gcode_state", "mc_percent", "subtask_name", "gcode_file")):
            ps = parse_print(self._state)
            if ps:
                key = f"{ps.gcode_state}|{ps.subtask_name}|{ps.progress_pct}"
                if key != self._last_print_key:
                    self._last_print_key = key
                    self._dispatch("print", ps)

    def _dispatch(self, kind: str, obj):
        if self._loop and self._handler and not self._stop.is_set():
            asyncio.run_coroutine_threadsafe(self._handler(kind, obj), self._loop)
