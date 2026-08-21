"""InventoryService — the only place that mutates spools from printer events."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..bus import bus
from ..models import AmsSlot, AppSettings, FilamentProduct, FilamentVariant, Print, PrintFilamentUsage, Spool, SpoolEvent
from ..printer.base import AmsSnapshot, PrintStatus, TrayState
from . import threemf

log = logging.getLogger("inventory")


def now() -> datetime:
    return datetime.now(timezone.utc)


def hex6(c: str | None) -> str | None:
    if not c:
        return None
    c = c.lstrip("#").upper()
    return c[:6] if len(c) >= 6 else None


async def get_settings(db: AsyncSession) -> AppSettings:
    s = await db.get(AppSettings, 1)
    if s is None:
        s = AppSettings(id=1)
        db.add(s)
        await db.flush()
    return s


def add_event(db: AsyncSession, spool: Spool, type_: str, delta: float | None = None, source="system", note=None, meta=None) -> SpoolEvent:
    ev = SpoolEvent(spool_id=spool.id, type=type_, delta_g=delta, remaining_g=spool.remaining_g, source=source, note=note, meta=meta)
    db.add(ev)
    return ev


async def ensure_slots(db: AsyncSession) -> dict[int, AmsSlot]:
    rows = (await db.execute(select(AmsSlot))).scalars().all()
    by = {r.slot_index: r for r in rows}
    for i in range(4):
        if i not in by:
            by[i] = AmsSlot(slot_index=i)
            db.add(by[i])
    await db.flush()
    return by


async def match_product(db: AsyncSession, sub_brands: str | None, tray_type: str | None) -> FilamentProduct | None:
    name = (sub_brands or tray_type or "").strip()
    if not name:
        return None
    p = (await db.execute(select(FilamentProduct).where(FilamentProduct.name.ilike(name)))).scalar_one_or_none()
    if p is None and tray_type:
        p = (await db.execute(select(FilamentProduct).where(FilamentProduct.name.ilike(f"{tray_type}%")).limit(1))).scalar_one_or_none()
    return p


async def match_variant(db: AsyncSession, product: FilamentProduct | None, colour_hex: str | None) -> FilamentVariant | None:
    if not product or not colour_hex:
        return None
    return (
        await db.execute(
            select(FilamentVariant).where(FilamentVariant.product_id == product.id, FilamentVariant.colour_hex == colour_hex)
        )
    ).scalars().first()


def colour_name_from(tray: TrayState, variant: FilamentVariant | None) -> str:
    if variant:
        return variant.colour_name
    return f"#{hex6(tray.tray_color)}" if tray.tray_color else "Unknown"


async def unclaimed_candidates(db: AsyncSession, tray: TrayState) -> list[Spool]:
    """Spools with no RFID id that match this tray's product + colour and are not loaded."""
    name = (tray.tray_sub_brands or tray.tray_type or "").strip()
    if not name:
        return []
    q = select(Spool).where(Spool.tray_uuid.is_(None), Spool.subtype.ilike(name), ~Spool.location.in_(["discarded"]), ~Spool.location.like("ams:%"))
    rows = (await db.execute(q)).scalars().all()
    hx = hex6(tray.tray_color)
    same_colour = [r for r in rows if hx and r.colour_hex == hx]
    return same_colour or rows


async def spool_from_tray(db: AsyncSession, tray: TrayState, slot_index: int) -> Spool:
    """Auto-create a spool for an unknown Bambu RFID tray."""
    product = await match_product(db, tray.tray_sub_brands, tray.tray_type)
    variant = await match_variant(db, product, hex6(tray.tray_color))
    weight = tray.tray_weight or 1000.0
    remaining = weight * (tray.remain_pct / 100) if tray.remain_pct is not None and tray.remain_pct >= 0 else weight
    spool = Spool(
        variant_id=variant.id if variant else None,
        product_id=product.id if product else None,
        tray_uuid=tray.tray_uuid,
        tag_uid=tray.tag_uid,
        brand="Bambu Lab",
        material=tray.tray_type or (product.material if product else "Unknown"),
        subtype=tray.tray_sub_brands or (product.name if product else tray.tray_type or "Unknown"),
        colour_name=colour_name_from(tray, variant),
        colour_hex=hex6(tray.tray_color) or (variant.colour_hex if variant else None),
        image_url=variant.image_url if variant else None,
        spool_type="spool",
        starting_weight_g=weight,
        remaining_g=round(remaining, 1),
        ams_remaining_pct=tray.remain_pct,
        location=f"ams:{slot_index}",
        opened=True,
        opened_at=now(),
        last_seen_at=now(),
    )
    db.add(spool)
    await db.flush()
    add_event(db, spool, "created", source="ams", note=f"Detected in AMS A{slot_index + 1}", meta={"tray_uuid": tray.tray_uuid})
    return spool


class InventoryService:
    def __init__(self, session_factory, printer_getter):
        self.session_factory = session_factory
        self.printer_getter = printer_getter  # callable -> PrinterLink | None
        self.last_ams: AmsSnapshot | None = None
        self.last_print: PrintStatus | None = None

    # ---------- entry point from PrinterManager ----------
    async def handle(self, kind: str, obj) -> None:
        try:
            async with self.session_factory() as db:
                if kind == "ams":
                    self.last_ams = obj
                    await self.apply_ams(db, obj)
                elif kind == "print":
                    await self.apply_print(db, obj)
                    self.last_print = obj
                await db.commit()
        except Exception:
            log.exception("error handling %s event", kind)

    # ---------- AMS ----------
    async def apply_ams(self, db: AsyncSession, snap: AmsSnapshot) -> None:
        slots = await ensure_slots(db)
        settings = await get_settings(db)
        changed_spools: set[int] = set()

        for tray in snap.trays:
            slot = slots[tray.slot_index]
            prev_spool_id = slot.spool_id
            prev_uuid = slot.tray_uuid
            slot.present = tray.present
            slot.tray_uuid = tray.tray_uuid
            slot.tag_uid = tray.tag_uid
            slot.tray_type = tray.tray_type
            slot.tray_sub_brands = tray.tray_sub_brands
            slot.tray_color = tray.tray_color
            slot.tray_weight = tray.tray_weight
            slot.remain_pct = tray.remain_pct
            slot.nozzle_temp_min = tray.nozzle_temp_min
            slot.nozzle_temp_max = tray.nozzle_temp_max
            slot.active = snap.active_tray == tray.slot_index

            new_spool: Spool | None = None
            if not tray.present:
                slot.spool_id = None
                slot.needs_identification = False
            elif tray.tray_uuid:
                new_spool = (await db.execute(select(Spool).where(Spool.tray_uuid == tray.tray_uuid))).scalars().first()
                if new_spool is None and prev_spool_id is not None and prev_uuid == tray.tray_uuid:
                    new_spool = await db.get(Spool, prev_spool_id)  # user-assigned earlier
                if new_spool is None:
                    # Spreadsheet-imported spools have no RFID id yet. If one looks like
                    # this tray, ask the user instead of creating a duplicate.
                    if await unclaimed_candidates(db, tray):
                        slot.spool_id = None
                        slot.needs_identification = True
                    else:
                        new_spool = await spool_from_tray(db, tray, tray.slot_index)
                        bus.publish("toast", {"kind": "info", "text": f"New Bambu spool added from AMS A{tray.slot_index + 1}: {new_spool.subtype} {new_spool.colour_name}"})
                if new_spool is not None:
                    slot.spool_id = new_spool.id
                    slot.needs_identification = False
            else:
                # Third-party tray: keep a manual assignment if the slot still has one, else ask.
                if prev_spool_id is not None and prev_uuid is None:
                    new_spool = await db.get(Spool, prev_spool_id)
                    slot.needs_identification = new_spool is None
                else:
                    slot.spool_id = None
                    slot.needs_identification = True

            if prev_spool_id and prev_spool_id != (new_spool.id if new_spool else None):
                old = await db.get(Spool, prev_spool_id)
                if old and old.location == f"ams:{tray.slot_index}":
                    old.location = "stored"
                    add_event(db, old, "unloaded", source="ams", note=f"Removed from AMS A{tray.slot_index + 1}")
                    changed_spools.add(old.id)

            if new_spool:
                loc = f"ams:{tray.slot_index}"
                if new_spool.location != loc:
                    # spool moved here (possibly from another slot)
                    new_spool.location = loc
                    if not new_spool.opened:
                        new_spool.opened = True
                        new_spool.opened_at = now()
                    add_event(db, new_spool, "loaded", source="ams", note=f"Loaded in AMS A{tray.slot_index + 1}")
                new_spool.last_seen_at = now()
                if tray.remain_pct is not None and tray.remain_pct >= 0:
                    new_spool.ams_remaining_pct = tray.remain_pct
                    calc = new_spool.remaining_pct
                    new_spool.ams_divergent = abs(calc - tray.remain_pct) > settings.divergence_pct
                if new_spool.colour_hex is None and tray.tray_color:
                    new_spool.colour_hex = hex6(tray.tray_color)
                if new_spool.tray_uuid is None and tray.tray_uuid:
                    new_spool.tray_uuid = tray.tray_uuid
                changed_spools.add(new_spool.id)

        await db.flush()
        bus.publish("ams", await serialize_slots(db))
        for sid in changed_spools:
            bus.publish("spool", {"id": sid})

    # ---------- Prints ----------
    async def apply_print(self, db: AsyncSession, ps: PrintStatus) -> None:
        running = (await db.execute(select(Print).where(Print.status == "running").order_by(Print.started_at.desc()))).scalars().first()
        state = ps.gcode_state

        if state in ("RUNNING", "PREPARE", "PAUSE") and ps.subtask_name:
            if running is None or running.subtask_name != ps.subtask_name:
                if running is not None:
                    # Previous job vanished without a FINISH/FAILED — leave it for the user.
                    running.status = "unresolved"
                    running.ended_at = now()
                running = await self._start_print(db, ps)
            else:
                running.progress_pct = ps.progress_pct
            bus.publish("print", {"id": running.id, "status": running.status, "progress_pct": running.progress_pct, "subtask_name": running.subtask_name})
            return

        if state == "FINISH" and running is not None:
            await self._finish_print(db, running, ok=True)
        elif state == "FAILED" and running is not None:
            running.progress_pct = ps.progress_pct
            await self._finish_print(db, running, ok=False)
        elif state == "IDLE" and running is not None and self.last_print and self.last_print.gcode_state in ("RUNNING", "PAUSE", "PREPARE"):
            # Cancelled prints go RUNNING -> IDLE on some firmwares.
            running.progress_pct = ps.progress_pct or running.progress_pct
            await self._finish_print(db, running, ok=False)

    async def _start_print(self, db: AsyncSession, ps: PrintStatus) -> Print:
        slots = await ensure_slots(db)
        snapshot = {str(i): s.spool_id for i, s in slots.items()}
        pr = Print(
            subtask_name=ps.subtask_name or "unknown",
            gcode_file=ps.gcode_file,
            plate_index=threemf.plate_index_from_gcode_file(ps.gcode_file),
            progress_pct=ps.progress_pct,
            slot_snapshot=snapshot,
        )
        db.add(pr)
        await db.flush()
        bus.publish("toast", {"kind": "info", "text": f"Print started: {pr.subtask_name}"})

        printer = self.printer_getter()
        data = None
        if printer is not None:
            try:
                data = await printer.fetch_3mf(pr.subtask_name, pr.gcode_file)
            except Exception as e:
                pr.fetch_error = f"{type(e).__name__}: {e}"
                log.warning("3mf fetch failed: %s", e)
        if data:
            try:
                plates = threemf.parse_3mf(data)
                plate = threemf.pick_plate(plates, pr.plate_index)
                if plate:
                    pr.three_mf_fetched = True
                    pr.planned_total_g = round(plate.total_g, 2)
                    for f in plate.filaments:
                        tray_index = self._map_filament_to_tray(f, ps, slots)
                        spool_id = slots[tray_index].spool_id if tray_index is not None else None
                        db.add(
                            PrintFilamentUsage(
                                print_id=pr.id,
                                filament_index=f.filament_index,
                                tray_index=tray_index,
                                spool_id=spool_id,
                                filament_type=f.type,
                                colour_hex=f.colour_hex,
                                planned_g=f.used_g,
                                planned_m=f.used_m,
                            )
                        )
            except Exception as e:
                pr.fetch_error = f"parse: {e}"
                log.warning("3mf parse failed: %s", e)
        elif not pr.fetch_error:
            pr.fetch_error = "3mf not available"
        await db.flush()
        return pr

    @staticmethod
    def _map_filament_to_tray(f: threemf.FilamentUsage, ps: PrintStatus, slots: dict[int, AmsSlot]) -> int | None:
        # 1. explicit mapping from the printer (index = filament_index-1 -> global tray id)
        if ps.ams_mapping and 0 <= f.filament_index - 1 < len(ps.ams_mapping):
            t = ps.ams_mapping[f.filament_index - 1]
            if 0 <= t < 4:
                return t
        # 2. match type + colour against loaded trays
        cands = [s for s in slots.values() if s.present]
        for s in cands:
            if (s.tray_type or "").upper() == (f.type or "").upper() and hex6(s.tray_color) == f.colour_hex:
                return s.slot_index
        # 3. match type only if unique
        same_type = [s for s in cands if (s.tray_type or "").upper() == (f.type or "").upper()]
        if len(same_type) == 1:
            return same_type[0].slot_index
        # 4. single loaded tray
        if len(cands) == 1:
            return cands[0].slot_index
        # 5. active tray
        active = [s for s in cands if s.active]
        return active[0].slot_index if active else None

    async def _finish_print(self, db: AsyncSession, pr: Print, ok: bool) -> None:
        pr.ended_at = now()
        usage = (await db.execute(select(PrintFilamentUsage).where(PrintFilamentUsage.print_id == pr.id))).scalars().all()
        if ok:
            pr.status = "finished"
            pr.progress_pct = 100
            await self.apply_usage(db, pr, usage, fraction=1.0, source="print")
            bus.publish("toast", {"kind": "success", "text": f"Print finished: {pr.subtask_name} — {pr.planned_total_g or 0:.1f} g deducted"})
        else:
            pr.status = "unresolved"
            bus.publish("toast", {"kind": "warn", "text": f"Print stopped at {pr.progress_pct}%: {pr.subtask_name}. Resolve it in Prints."})
        bus.publish("print", {"id": pr.id, "status": pr.status, "progress_pct": pr.progress_pct, "subtask_name": pr.subtask_name})

    async def apply_usage(self, db: AsyncSession, pr: Print, usage: list[PrintFilamentUsage], fraction: float, source: str) -> None:
        for u in usage:
            if u.applied_at is not None or u.spool_id is None:
                continue
            spool = await db.get(Spool, u.spool_id)
            if spool is None:
                continue
            grams = round(u.planned_g * fraction, 2)
            spool.remaining_g = round(max(0.0, spool.remaining_g - grams), 2)
            u.applied_g = grams
            u.applied_at = now()
            add_event(db, spool, "print_usage", delta=-grams, source=source, note=pr.subtask_name, meta={"print_id": pr.id, "fraction": fraction})
            bus.publish("spool", {"id": spool.id})
        await db.flush()


# ---------- serializers shared with routers ----------
async def serialize_slots(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(AmsSlot).options(selectinload(AmsSlot.spool)).order_by(AmsSlot.slot_index))).scalars().all()
    out = []
    for s in rows:
        out.append(
            {
                "slot_index": s.slot_index,
                "label": s.label,
                "present": s.present,
                "active": s.active,
                "tray_uuid": s.tray_uuid,
                "tray_type": s.tray_type,
                "tray_sub_brands": s.tray_sub_brands,
                "tray_color": hex6(s.tray_color),
                "tray_weight": s.tray_weight,
                "remain_pct": s.remain_pct,
                "nozzle_temp_min": s.nozzle_temp_min,
                "nozzle_temp_max": s.nozzle_temp_max,
                "needs_identification": s.needs_identification,
                "spool": spool_summary(s.spool) if s.spool else None,
                "updated_at": s.updated_at,
            }
        )
    return out


def spool_summary(s: Spool) -> dict:
    return {
        "id": s.id,
        "brand": s.brand,
        "material": s.material,
        "subtype": s.subtype,
        "colour_name": s.colour_name,
        "colour_hex": s.colour_hex,
        "image_url": s.image_url,
        "spool_type": s.spool_type,
        "starting_weight_g": s.starting_weight_g,
        "remaining_g": s.remaining_g,
        "remaining_pct": round(s.remaining_pct, 1),
        "ams_remaining_pct": s.ams_remaining_pct,
        "ams_divergent": s.ams_divergent,
        "location": s.location,
        "opened": s.opened,
        "tray_uuid": s.tray_uuid,
        "variant_id": s.variant_id,
        "product_id": s.product_id,
        "created_at": s.created_at,
        "last_seen_at": s.last_seen_at,
        "opened_at": s.opened_at,
        "purchased_at": s.purchased_at,
        "notes": s.notes,
    }
