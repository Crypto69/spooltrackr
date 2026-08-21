"""Owns the active PrinterLink and restarts it when settings change."""
from __future__ import annotations

import asyncio
import logging

from ..bus import bus
from ..config import settings as env
from .bambu import BambuPrinter
from .base import PrinterLink, PrinterStatus
from .mock import MockPrinter

log = logging.getLogger("printer.manager")


class PrinterManager:
    def __init__(self, inventory):
        self.inventory = inventory
        self.link: PrinterLink | None = None
        self.mode = "off"
        self._lock = asyncio.Lock()

    def status(self) -> PrinterStatus:
        if self.link is None:
            return PrinterStatus(connected=False, mode=self.mode, message="Printer link off")
        return self.link.status

    async def configure(self, mode: str, host: str, serial: str, access_code: str) -> None:
        async with self._lock:
            if self.link is not None:
                await self.link.stop()
                self.link = None
            self.mode = mode
            if mode == "mock":
                self.link = MockPrinter()
            elif mode == "live":
                if not (host and serial and access_code):
                    log.warning("live mode selected but host/serial/access code missing")
                    bus.publish("printer", {"connected": False, "mode": mode, "message": "Missing host, serial or access code"})
                    return
                self.link = BambuPrinter(host, serial, access_code)
            else:
                bus.publish("printer", self.status().__dict__)
                return
            await self.link.start(asyncio.get_running_loop(), self.inventory.handle)
            bus.publish("printer", self.status().__dict__)

    async def stop(self):
        if self.link:
            await self.link.stop()
            self.link = None

    def mock(self) -> MockPrinter | None:
        return self.link if isinstance(self.link, MockPrinter) else None
