"""A fake X1C for development and UI tests. Drive it via /api/debug/mock/*."""
from __future__ import annotations

import asyncio
import zipfile
import io
from dataclasses import dataclass, field

from .base import AmsSnapshot, EventHandler, PrintStatus, PrinterStatus, TrayState

MOCK_UUIDS = {
    0: "FB9363D5A52340FB82E133A8CBDBFC31",  # PLA Basic Jade White
    1: "8AC28D1E3C6B4E1EA2D3F1B9C0A7E5D2",  # PLA Basic Black
    2: "729A11F0C4DE4B1D9F3A6C8E2B5D7A90",  # PLA Matte Latte Brown (refill)
}


@dataclass
class MockPrinter:
    status: PrinterStatus = field(default_factory=lambda: PrinterStatus(connected=True, mode="mock", message="Mock printer"))
    trays: dict[int, TrayState] = field(default_factory=dict)
    active_tray: int | None = None
    current: PrintStatus | None = None
    _handler: EventHandler | None = None
    _loop: asyncio.AbstractEventLoop | None = None

    async def start(self, loop, handler):
        self._loop = loop
        self._handler = handler
        if not self.trays:
            self.trays = {
                0: TrayState(0, True, MOCK_UUIDS[0], "AA01", "PLA", "PLA Basic", "FFFFFFFF", 1000, 82, 190, 230, "GFA00"),
                1: TrayState(1, True, MOCK_UUIDS[1], "AA02", "PLA", "PLA Basic", "000000FF", 1000, 64, 190, 230, "GFA00"),
                2: TrayState(2, False),
                3: TrayState(3, True, None, None, "PETG", "PETG", "FF6600FF", 1000, None, 230, 260, None),  # third-party, no RFID
            }
        await self._emit_ams()

    async def stop(self):
        pass

    async def _emit_ams(self):
        if self._handler:
            trays = [self.trays.get(i, TrayState(i, False)) for i in range(4)]
            await self._handler("ams", AmsSnapshot(trays=trays, active_tray=self.active_tray))

    async def _emit_print(self):
        if self._handler and self.current:
            await self._handler("print", self.current)

    # --- control surface used by /api/debug/mock ---
    async def load(self, slot: int, tray_uuid: str | None, tray_type: str, sub_brands: str, colour: str, remain: int | None = 100, weight=1000):
        self.trays[slot] = TrayState(slot, True, tray_uuid, None, tray_type, sub_brands, colour, weight, remain)
        await self._emit_ams()

    async def unload(self, slot: int):
        self.trays[slot] = TrayState(slot, False)
        await self._emit_ams()

    async def start_print(self, name: str, filaments: list[dict], ams_mapping: list[int] | None = None):
        self._pending_3mf = _build_fake_3mf(filaments)
        self.current = PrintStatus("RUNNING", name, "/data/Metadata/plate_1.gcode", 0, ams_mapping=ams_mapping)
        self.active_tray = ams_mapping[0] if ams_mapping else 0
        await self._emit_print()
        await self._emit_ams()

    async def progress(self, pct: int):
        if self.current:
            self.current.progress_pct = pct
            await self._emit_print()

    async def finish(self, ok: bool = True):
        if self.current:
            self.current.gcode_state = "FINISH" if ok else "FAILED"
            if ok:
                self.current.progress_pct = 100
            await self._emit_print()
            self.current = None
            self.active_tray = None
            await self._emit_ams()

    async def fetch_3mf(self, subtask_name: str, gcode_file: str | None) -> bytes | None:
        return getattr(self, "_pending_3mf", None)


def _build_fake_3mf(filaments: list[dict]) -> bytes:
    rows = "".join(
        f'    <filament id="{i + 1}" tray_info_idx="GFA00" type="{f.get("type", "PLA")}" color="#{f.get("color", "FFFFFF")}" used_m="{f.get("used_m", 10)}" used_g="{f["used_g"]}" />\n'
        for i, f in enumerate(filaments)
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="printer_model_id" value="BL-P001"/>
{rows}  </plate>
</config>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Metadata/slice_info.config", xml)
    return buf.getvalue()
