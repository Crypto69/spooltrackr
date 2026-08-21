from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from ..bus import bus
from ..config import settings as env
from ..db import get_session
from ..models import AmsSlot, FilamentProduct, FilamentVariant, Print, PrintFilamentUsage, Spool, SpoolEvent
from ..services import catalog
from ..services.inventory import add_event, ensure_slots, get_settings, hex6, serialize_slots, spool_summary

router = APIRouter(prefix="/api")


def now():
    return datetime.now(timezone.utc)


def svc(request: Request):
    return request.app.state.inventory


def mgr(request: Request):
    return request.app.state.printer


# ---------------- meta / live ----------------
@router.get("/version")
async def version():
    return {"sha": env.build_sha, "built": env.build_time, "name": "spooltrackr"}


@router.get("/events")
async def events(request: Request):
    q = bus.subscribe()

    async def gen():
        try:
            yield {"event": "hello", "data": bus.encode({"ok": True})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": msg["event"], "data": bus.encode(msg["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(gen())


@router.get("/state")
async def state(request: Request, db: AsyncSession = Depends(get_session)):
    await ensure_slots(db)
    await db.commit()
    s = await get_settings(db)
    running = (await db.execute(select(Print).where(Print.status == "running").order_by(Print.started_at.desc()))).scalars().first()
    low = (
        await db.execute(
            select(func.count()).select_from(Spool).where(
                Spool.location != "discarded",
                (Spool.remaining_g < s.low_g) | (Spool.remaining_g / Spool.starting_weight_g * 100 < s.low_pct),
            )
        )
    ).scalar_one()
    unresolved = (await db.execute(select(func.count()).select_from(Print).where(Print.status == "unresolved"))).scalar_one()
    return {
        "printer": mgr(request).status().__dict__,
        "slots": await serialize_slots(db),
        "active_print": print_summary(running) if running else None,
        "low_count": low,
        "unresolved_prints": unresolved,
        "thresholds": {"low_pct": s.low_pct, "low_g": s.low_g},
    }


# ---------------- spools ----------------
class SpoolIn(BaseModel):
    brand: str = "Bambu Lab"
    material: str
    subtype: str
    colour_name: str
    colour_hex: str | None = None
    image_url: str | None = None
    spool_type: str = "spool"
    starting_weight_g: float = 1000
    remaining_g: float | None = None
    location: str = "stored"
    opened: bool = False
    notes: str | None = None
    variant_id: int | None = None
    product_id: int | None = None
    tray_uuid: str | None = None
    purchased_at: datetime | None = None


class SpoolPatch(BaseModel):
    brand: str | None = None
    material: str | None = None
    subtype: str | None = None
    colour_name: str | None = None
    colour_hex: str | None = None
    image_url: str | None = None
    spool_type: str | None = None
    starting_weight_g: float | None = None
    location: str | None = None
    opened: bool | None = None
    notes: str | None = None
    variant_id: int | None = None
    product_id: int | None = None
    tray_uuid: str | None = None
    purchased_at: datetime | None = None


@router.get("/spools")
async def list_spools(
    db: AsyncSession = Depends(get_session),
    include_discarded: bool = False,
):
    q = select(Spool).options(selectinload(Spool.product)).order_by(Spool.subtype, Spool.colour_name, Spool.id)
    if not include_discarded:
        q = q.where(Spool.location != "discarded")
    rows = (await db.execute(q)).scalars().all()
    return [spool_summary(s) for s in rows]


@router.post("/spools", status_code=201)
async def create_spool(body: SpoolIn, db: AsyncSession = Depends(get_session)):
    data = body.model_dump()
    if data.get("remaining_g") is None:
        data["remaining_g"] = data["starting_weight_g"]
    data["colour_hex"] = hex6(data.get("colour_hex"))
    if body.variant_id:
        var = await db.get(FilamentVariant, body.variant_id)
        if var:
            data.setdefault("image_url", None)
            data["image_url"] = data["image_url"] or var.image_url
            data["colour_hex"] = data["colour_hex"] or var.colour_hex
            data["product_id"] = data["product_id"] or var.product_id
    if data.get("opened"):
        data["opened_at"] = now()
    s = Spool(**data)
    db.add(s)
    await db.flush()
    add_event(db, s, "created", source="user", note="Added manually")
    await db.commit()
    bus.publish("spool", {"id": s.id})
    return spool_summary(s)


async def _get_spool(db: AsyncSession, spool_id: int) -> Spool:
    s = await db.get(Spool, spool_id)
    if not s:
        raise HTTPException(404, "spool not found")
    return s


@router.get("/spools/{spool_id}")
async def get_spool(spool_id: int, db: AsyncSession = Depends(get_session)):
    s = (
        await db.execute(select(Spool).where(Spool.id == spool_id).options(selectinload(Spool.events), selectinload(Spool.product), selectinload(Spool.variant)))
    ).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "spool not found")
    usage = (
        await db.execute(
            select(PrintFilamentUsage, Print)
            .join(Print, Print.id == PrintFilamentUsage.print_id)
            .where(PrintFilamentUsage.spool_id == spool_id)
            .order_by(Print.started_at.desc())
        )
    ).all()
    out = spool_summary(s)
    out["product"] = product_out(s.product) if s.product else None
    out["variant"] = variant_out(s.variant) if s.variant else None
    out["events"] = [event_out(e) for e in s.events]
    out["prints"] = [
        {"print_id": p.id, "subtask_name": p.subtask_name, "status": p.status, "started_at": p.started_at, "planned_g": u.planned_g, "applied_g": u.applied_g}
        for u, p in usage
    ]
    out["total_used_g"] = round(sum(-(e.delta_g or 0) for e in s.events if e.type == "print_usage"), 1)
    return out


@router.patch("/spools/{spool_id}")
async def patch_spool(spool_id: int, body: SpoolPatch, db: AsyncSession = Depends(get_session)):
    s = await _get_spool(db, spool_id)
    data = body.model_dump(exclude_unset=True)
    if "colour_hex" in data:
        data["colour_hex"] = hex6(data["colour_hex"])
    if data.get("opened") and not s.opened:
        s.opened_at = now()
    if "starting_weight_g" in data and data["starting_weight_g"] and s.remaining_g > data["starting_weight_g"]:
        s.remaining_g = data["starting_weight_g"]
    if data.get("variant_id"):
        var = await db.get(FilamentVariant, data["variant_id"])
        if var:
            data.setdefault("image_url", var.image_url)
            data.setdefault("colour_hex", var.colour_hex)
            data.setdefault("product_id", var.product_id)
    for k, v in data.items():
        setattr(s, k, v)
    await db.commit()
    bus.publish("spool", {"id": s.id})
    return spool_summary(s)


class AdjustIn(BaseModel):
    remaining_g: float | None = None
    delta_g: float | None = None
    note: str | None = None
    use_ams: bool = False


@router.post("/spools/{spool_id}/adjust")
async def adjust_spool(spool_id: int, body: AdjustIn, db: AsyncSession = Depends(get_session)):
    s = await _get_spool(db, spool_id)
    before = s.remaining_g
    if body.use_ams:
        if s.ams_remaining_pct is None:
            raise HTTPException(400, "no AMS estimate for this spool")
        s.remaining_g = round(s.starting_weight_g * s.ams_remaining_pct / 100, 1)
        typ, src = "ams_reconciliation", "ams"
    elif body.remaining_g is not None:
        s.remaining_g = min(s.starting_weight_g, max(0.0, float(body.remaining_g)))
        typ, src = "manual_adjustment", "user"
    elif body.delta_g is not None:
        s.remaining_g = min(s.starting_weight_g, max(0.0, s.remaining_g + float(body.delta_g)))
        typ, src = "manual_adjustment", "user"
    else:
        raise HTTPException(400, "remaining_g, delta_g or use_ams required")
    if s.ams_remaining_pct is not None:
        st = await get_settings(db)
        s.ams_divergent = abs(s.remaining_pct - s.ams_remaining_pct) > st.divergence_pct
    add_event(db, s, typ, delta=round(s.remaining_g - before, 2), source=src, note=body.note)
    await db.commit()
    bus.publish("spool", {"id": s.id})
    return spool_summary(s)


class RefillIn(BaseModel):
    variant_id: int | None = None
    subtype: str | None = None
    colour_name: str | None = None
    colour_hex: str | None = None
    starting_weight_g: float = 1000
    note: str | None = None


@router.post("/spools/{spool_id}/refill")
async def refill_spool(spool_id: int, body: RefillIn, db: AsyncSession = Depends(get_session)):
    """Same physical spool hardware (and RFID), new filament on it."""
    s = await _get_spool(db, spool_id)
    old = f"{s.subtype} {s.colour_name} ({s.remaining_g:.0f} g left)"
    if body.variant_id:
        var = await db.get(FilamentVariant, body.variant_id)
        if var:
            prod = await db.get(FilamentProduct, var.product_id)
            s.variant_id, s.product_id = var.id, var.product_id
            s.subtype, s.material = prod.name, prod.material
            s.colour_name, s.colour_hex, s.image_url = var.colour_name, var.colour_hex, var.image_url
    if body.subtype:
        s.subtype = body.subtype
    if body.colour_name:
        s.colour_name = body.colour_name
    if body.colour_hex:
        s.colour_hex = hex6(body.colour_hex)
    s.starting_weight_g = body.starting_weight_g
    s.remaining_g = body.starting_weight_g
    s.ams_remaining_pct = None
    s.ams_divergent = False
    s.opened, s.opened_at = True, now()
    add_event(db, s, "refill", delta=body.starting_weight_g, source="user", note=body.note or f"Refilled. Previously {old}")
    await db.commit()
    bus.publish("spool", {"id": s.id})
    return spool_summary(s)


@router.post("/spools/{spool_id}/discard")
async def discard_spool(spool_id: int, db: AsyncSession = Depends(get_session)):
    s = await _get_spool(db, spool_id)
    s.location = "discarded"
    add_event(db, s, "discarded", source="user")
    slots = await ensure_slots(db)
    for sl in slots.values():
        if sl.spool_id == s.id:
            sl.spool_id = None
    await db.commit()
    bus.publish("spool", {"id": s.id})
    return spool_summary(s)


@router.delete("/spools/{spool_id}", status_code=204)
async def delete_spool(spool_id: int, db: AsyncSession = Depends(get_session)):
    s = await _get_spool(db, spool_id)
    await db.delete(s)
    await db.commit()
    bus.publish("spool", {"id": spool_id, "deleted": True})


# ---------------- AMS ----------------
@router.get("/ams")
async def ams(db: AsyncSession = Depends(get_session)):
    await ensure_slots(db)
    await db.commit()
    return await serialize_slots(db)


class AssignIn(BaseModel):
    spool_id: int | None = None
    create: SpoolIn | None = None


@router.post("/ams/{slot_index}/assign")
async def assign_slot(slot_index: int, body: AssignIn, db: AsyncSession = Depends(get_session)):
    slots = await ensure_slots(db)
    if slot_index not in slots:
        raise HTTPException(404, "slot")
    slot = slots[slot_index]
    if body.create:
        data = body.create.model_dump()
        data["remaining_g"] = data.get("remaining_g") or data["starting_weight_g"]
        data["colour_hex"] = hex6(data.get("colour_hex")) or hex6(slot.tray_color)
        data["opened"], data["opened_at"] = True, now()
        spool = Spool(**data)
        db.add(spool)
        await db.flush()
        add_event(db, spool, "created", source="user", note=f"Created for AMS {slot.label}")
    elif body.spool_id:
        spool = await _get_spool(db, body.spool_id)
    else:
        raise HTTPException(400, "spool_id or create required")
    # unload whatever was there / wherever this spool was
    for other in slots.values():
        if other.spool_id == spool.id and other.slot_index != slot_index:
            other.spool_id = None
    if slot.spool_id and slot.spool_id != spool.id:
        old = await db.get(Spool, slot.spool_id)
        if old:
            old.location = "stored"
            add_event(db, old, "unloaded", source="user", note=f"Replaced in AMS {slot.label}")
    slot.spool_id = spool.id
    slot.needs_identification = False
    if slot.tray_uuid and not spool.tray_uuid:
        spool.tray_uuid = slot.tray_uuid  # claim the RFID identity for this physical spool
        spool.tag_uid = slot.tag_uid
    spool.location = f"ams:{slot_index}"
    spool.opened = True
    spool.last_seen_at = now()
    if slot.remain_pct is not None:
        spool.ams_remaining_pct = slot.remain_pct
    add_event(db, spool, "loaded", source="user", note=f"Assigned to AMS {slot.label}")
    await db.commit()
    bus.publish("ams", await serialize_slots(db))
    bus.publish("spool", {"id": spool.id})
    return await serialize_slots(db)


@router.get("/ams/{slot_index}/candidates")
async def slot_candidates(slot_index: int, db: AsyncSession = Depends(get_session)):
    """Spools that could be the unidentified tray in this slot (best matches first)."""
    from ..printer.base import TrayState
    from ..services.inventory import unclaimed_candidates

    slots = await ensure_slots(db)
    slot = slots.get(slot_index)
    if slot is None:
        raise HTTPException(404, "slot")
    tray = TrayState(slot_index, slot.present, slot.tray_uuid, slot.tag_uid, slot.tray_type, slot.tray_sub_brands, slot.tray_color)
    best = await unclaimed_candidates(db, tray)
    best_ids = {s.id for s in best}
    others = (
        await db.execute(select(Spool).where(Spool.location != "discarded", ~Spool.location.like("ams:%"), Spool.id.notin_(best_ids)).order_by(Spool.subtype, Spool.colour_name))
    ).scalars().all()
    return {"best": [spool_summary(s) for s in best], "others": [spool_summary(s) for s in others]}


@router.post("/ams/{slot_index}/unassign")
async def unassign_slot(slot_index: int, db: AsyncSession = Depends(get_session)):
    slots = await ensure_slots(db)
    slot = slots.get(slot_index)
    if slot is None:
        raise HTTPException(404, "slot")
    if slot.spool_id:
        old = await db.get(Spool, slot.spool_id)
        if old:
            old.location = "stored"
            add_event(db, old, "unloaded", source="user", note=f"Unassigned from AMS {slot.label}")
    slot.spool_id = None
    slot.needs_identification = slot.present
    await db.commit()
    bus.publish("ams", await serialize_slots(db))
    return await serialize_slots(db)


# ---------------- prints ----------------
def print_summary(p: Print) -> dict:
    return {
        "id": p.id,
        "subtask_name": p.subtask_name,
        "gcode_file": p.gcode_file,
        "plate_index": p.plate_index,
        "started_at": p.started_at,
        "ended_at": p.ended_at,
        "status": p.status,
        "progress_pct": p.progress_pct,
        "planned_total_g": p.planned_total_g,
        "three_mf_fetched": p.three_mf_fetched,
        "fetch_error": p.fetch_error,
    }


@router.get("/prints")
async def list_prints(db: AsyncSession = Depends(get_session), limit: int = 100):
    rows = (
        await db.execute(select(Print).options(selectinload(Print.usage).selectinload(PrintFilamentUsage.spool)).order_by(Print.started_at.desc()).limit(limit))
    ).scalars().all()
    out = []
    for p in rows:
        d = print_summary(p)
        d["usage"] = [usage_out(u) for u in p.usage]
        out.append(d)
    return out


def usage_out(u: PrintFilamentUsage) -> dict:
    return {
        "id": u.id,
        "filament_index": u.filament_index,
        "tray_index": u.tray_index,
        "spool_id": u.spool_id,
        "spool": spool_summary(u.spool) if u.spool else None,
        "filament_type": u.filament_type,
        "colour_hex": u.colour_hex,
        "planned_g": u.planned_g,
        "planned_m": u.planned_m,
        "applied_g": u.applied_g,
        "applied_at": u.applied_at,
    }


class ResolveIn(BaseModel):
    fraction: float = Field(ge=0, le=1)
    note: str | None = None


@router.post("/prints/{print_id}/resolve")
async def resolve_print(print_id: int, body: ResolveIn, request: Request, db: AsyncSession = Depends(get_session)):
    p = await db.get(Print, print_id)
    if not p:
        raise HTTPException(404)
    if p.status not in ("unresolved", "running"):
        raise HTTPException(400, "print already resolved")
    usage = (await db.execute(select(PrintFilamentUsage).where(PrintFilamentUsage.print_id == p.id))).scalars().all()
    await svc(request).apply_usage(db, p, usage, fraction=body.fraction, source="user")
    p.status = "resolved"
    p.ended_at = p.ended_at or now()
    await db.commit()
    bus.publish("print", {"id": p.id, "status": p.status})
    return print_summary(p)


class UsageSpoolIn(BaseModel):
    spool_id: int | None


@router.patch("/prints/{print_id}/usage/{usage_id}")
async def reassign_usage(print_id: int, usage_id: int, body: UsageSpoolIn, db: AsyncSession = Depends(get_session)):
    u = await db.get(PrintFilamentUsage, usage_id)
    if not u or u.print_id != print_id:
        raise HTTPException(404)
    if u.applied_at is not None:
        raise HTTPException(400, "usage already applied; adjust the spools manually")
    u.spool_id = body.spool_id
    await db.commit()
    return {"ok": True}


@router.delete("/prints/{print_id}", status_code=204)
async def delete_print(print_id: int, db: AsyncSession = Depends(get_session)):
    p = await db.get(Print, print_id)
    if p:
        await db.delete(p)
        await db.commit()


# ---------------- catalog ----------------
def product_out(p: FilamentProduct) -> dict:
    return {c.name: getattr(p, c.name) for c in FilamentProduct.__table__.columns}


def variant_out(v: FilamentVariant) -> dict:
    return {c.name: getattr(v, c.name) for c in FilamentVariant.__table__.columns}


def event_out(e: SpoolEvent) -> dict:
    return {"id": e.id, "type": e.type, "delta_g": e.delta_g, "remaining_g": e.remaining_g, "source": e.source, "note": e.note, "meta": e.meta, "created_at": e.created_at}


@router.get("/catalog/products")
async def products(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(FilamentProduct).options(selectinload(FilamentProduct.variants)).order_by(FilamentProduct.material, FilamentProduct.name))).scalars().all()
    out = []
    for p in rows:
        d = product_out(p)
        d["variants"] = sorted((variant_out(v) for v in p.variants), key=lambda v: v["colour_name"])
        out.append(d)
    return out


class ProductPatch(BaseModel):
    model_config = {"extra": "allow"}


@router.patch("/catalog/products/{product_id}")
async def patch_product(product_id: int, body: dict[str, Any], db: AsyncSession = Depends(get_session)):
    p = await db.get(FilamentProduct, product_id)
    if not p:
        raise HTTPException(404)
    allowed = {c.name for c in FilamentProduct.__table__.columns} - {"id"}
    for k, v in body.items():
        if k in allowed:
            setattr(p, k, v)
    await db.commit()
    return product_out(p)


@router.post("/catalog/products", status_code=201)
async def create_product(body: dict[str, Any], db: AsyncSession = Depends(get_session)):
    allowed = {c.name for c in FilamentProduct.__table__.columns} - {"id"}
    p = FilamentProduct(**{k: v for k, v in body.items() if k in allowed})
    db.add(p)
    await db.commit()
    return product_out(p)


@router.patch("/catalog/variants/{variant_id}")
async def patch_variant(variant_id: int, body: dict[str, Any], db: AsyncSession = Depends(get_session)):
    v = await db.get(FilamentVariant, variant_id)
    if not v:
        raise HTTPException(404)
    allowed = {"colour_name", "colour_code", "colour_hex", "image_url"}
    for k, val in body.items():
        if k in allowed:
            setattr(v, k, hex6(val) if k == "colour_hex" else val)
    await db.commit()
    return variant_out(v)


@router.post("/catalog/sync")
async def sync(db: AsyncSession = Depends(get_session)):
    stats = await catalog.sync_catalog(db)
    bus.publish("catalog", stats)
    return stats


# ---------------- settings ----------------
class SettingsIn(BaseModel):
    printer_mode: str | None = None
    printer_host: str | None = None
    printer_serial: str | None = None
    printer_access_code: str | None = None
    low_pct: int | None = None
    low_g: int | None = None
    divergence_pct: int | None = None
    store_region: str | None = None
    store_handles: list[str] | None = None


def settings_out(s) -> dict:
    return {
        "printer_mode": s.printer_mode,
        "printer_host": s.printer_host,
        "printer_serial": s.printer_serial,
        "printer_access_code": s.printer_access_code,
        "low_pct": s.low_pct,
        "low_g": s.low_g,
        "divergence_pct": s.divergence_pct,
        "store_region": s.store_region,
        "store_handles": s.store_handles or [],
        "catalog_last_sync_at": s.catalog_last_sync_at,
        "catalog_last_sync_log": s.catalog_last_sync_log,
    }


@router.get("/settings")
async def read_settings(db: AsyncSession = Depends(get_session)):
    s = await get_settings(db)
    await db.commit()
    return settings_out(s)


@router.put("/settings")
async def write_settings(body: SettingsIn, request: Request, db: AsyncSession = Depends(get_session)):
    s = await get_settings(db)
    data = body.model_dump(exclude_unset=True)
    printer_keys = {"printer_mode", "printer_host", "printer_serial", "printer_access_code"}
    reconnect = any(k in data and getattr(s, k) != data[k] for k in printer_keys)
    for k, v in data.items():
        setattr(s, k, v)
    await db.commit()
    if reconnect:
        await mgr(request).configure(s.printer_mode, s.printer_host, s.printer_serial, s.printer_access_code)
    return settings_out(s)


@router.post("/settings/reconnect")
async def reconnect(request: Request, db: AsyncSession = Depends(get_session)):
    s = await get_settings(db)
    await mgr(request).configure(s.printer_mode, s.printer_host, s.printer_serial, s.printer_access_code)
    return mgr(request).status().__dict__


# ---------------- mock printer controls (mock mode only) ----------------
class MockLoad(BaseModel):
    slot: int
    tray_uuid: str | None = None
    tray_type: str = "PLA"
    sub_brands: str = "PLA Basic"
    colour: str = "FFFFFFFF"
    remain: int | None = 100
    weight: float = 1000


class MockPrint(BaseModel):
    name: str = "Test Print"
    filaments: list[dict] = Field(default_factory=lambda: [{"type": "PLA", "color": "FFFFFF", "used_g": 42.5, "used_m": 14.2}])
    ams_mapping: list[int] | None = None


@router.post("/debug/mock/{action}")
async def mock_action(action: str, request: Request, body: dict[str, Any] | None = None):
    m = mgr(request).mock()
    if m is None:
        raise HTTPException(400, "printer is not in mock mode")
    body = body or {}
    if action == "load":
        b = MockLoad(**body)
        await m.load(b.slot, b.tray_uuid, b.tray_type, b.sub_brands, b.colour, b.remain, b.weight)
    elif action == "unload":
        await m.unload(int(body.get("slot", 0)))
    elif action == "start":
        b = MockPrint(**body)
        await m.start_print(b.name, b.filaments, b.ams_mapping)
    elif action == "progress":
        await m.progress(int(body.get("pct", 50)))
    elif action == "finish":
        await m.finish(ok=True)
    elif action == "fail":
        await m.finish(ok=False)
    else:
        raise HTTPException(404, "unknown action")
    return {"ok": True}
