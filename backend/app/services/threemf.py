"""Parse filament usage out of a Bambu .gcode.3mf (Metadata/slice_info.config)."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET


@dataclass
class FilamentUsage:
    filament_index: int  # slicer filament id, 1-based
    type: str
    colour_hex: str | None
    used_g: float
    used_m: float | None
    tray_info_idx: str | None = None


@dataclass
class PlateUsage:
    plate_index: int
    filaments: list[FilamentUsage]

    @property
    def total_g(self) -> float:
        return sum(f.used_g for f in self.filaments)


def _norm_hex(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lstrip("#").upper()
    return v[:6] if len(v) >= 6 else None


def parse_slice_info(xml_text: str) -> list[PlateUsage]:
    root = ET.fromstring(xml_text)
    plates: list[PlateUsage] = []
    for plate in root.iter("plate"):
        idx = None
        for meta in plate.findall("metadata"):
            if meta.get("key") == "index":
                try:
                    idx = int(meta.get("value", "0"))
                except ValueError:
                    idx = None
        filaments = []
        for f in plate.findall("filament"):
            try:
                filaments.append(
                    FilamentUsage(
                        filament_index=int(f.get("id", "0")),
                        type=f.get("type", "") or "",
                        colour_hex=_norm_hex(f.get("color")),
                        used_g=float(f.get("used_g", "0") or 0),
                        used_m=float(f.get("used_m")) if f.get("used_m") else None,
                        tray_info_idx=f.get("tray_info_idx"),
                    )
                )
            except ValueError:
                continue
        plates.append(PlateUsage(plate_index=idx or len(plates) + 1, filaments=filaments))
    return plates


def parse_3mf(data: bytes) -> list[PlateUsage]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next((n for n in zf.namelist() if n.endswith("Metadata/slice_info.config")), None)
        if not name:
            raise ValueError("slice_info.config not found in 3mf")
        return parse_slice_info(zf.read(name).decode("utf-8", errors="replace"))


def plate_index_from_gcode_file(gcode_file: str | None) -> int | None:
    """'/data/Metadata/plate_2.gcode' -> 2"""
    if not gcode_file:
        return None
    m = re.search(r"plate_(\d+)", gcode_file)
    return int(m.group(1)) if m else None


def pick_plate(plates: list[PlateUsage], plate_index: int | None) -> PlateUsage | None:
    if not plates:
        return None
    if plate_index is not None:
        for p in plates:
            if p.plate_index == plate_index:
                return p
    # fall back to the plate that actually has filament usage
    with_usage = [p for p in plates if p.filaments]
    return with_usage[0] if with_usage else plates[0]
