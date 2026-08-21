"""Normalised printer events. Both the mock and the live Bambu link emit these."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol


@dataclass
class TrayState:
    slot_index: int
    present: bool
    tray_uuid: str | None = None
    tag_uid: str | None = None
    tray_type: str | None = None  # PLA
    tray_sub_brands: str | None = None  # "PLA Basic"
    tray_color: str | None = None  # RRGGBBAA
    tray_weight: float | None = None
    remain_pct: int | None = None
    nozzle_temp_min: int | None = None
    nozzle_temp_max: int | None = None
    tray_info_idx: str | None = None


@dataclass
class AmsSnapshot:
    trays: list[TrayState]
    active_tray: int | None = None  # tray_now (0..3) or None


@dataclass
class PrintStatus:
    gcode_state: str  # IDLE RUNNING PAUSE FINISH FAILED PREPARE
    subtask_name: str | None
    gcode_file: str | None
    progress_pct: int
    ams_mapping: list[int] | None = None
    layer_num: int | None = None
    remaining_minutes: int | None = None


@dataclass
class PrinterStatus:
    connected: bool
    mode: str
    message: str = ""
    nozzle_temp: float | None = None
    bed_temp: float | None = None
    last_message_at: str | None = None
    extra: dict = field(default_factory=dict)


EventHandler = Callable[[str, object], Awaitable[None]]


class PrinterLink(Protocol):
    status: PrinterStatus

    async def start(self, loop: asyncio.AbstractEventLoop, handler: EventHandler) -> None: ...
    async def stop(self) -> None: ...
    async def fetch_3mf(self, subtask_name: str, gcode_file: str | None) -> bytes | None: ...
