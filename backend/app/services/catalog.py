"""Sync products/variants from the Bambu store into the DB."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FilamentProduct, FilamentVariant, Spool
from . import store
from .inventory import get_settings

log = logging.getLogger("catalog")


def material_from_name(name: str) -> str:
    n = name.upper()
    for m in ("PLA", "PETG", "PET", "ABS", "ASA", "TPU", "PC", "PAHT", "PPA", "PPS", "PA6", "PA", "PVA", "SUPPORT"):
        if n.startswith(m):
            return "PA" if m in ("PAHT", "PA6") else m
    return n.split()[0] if n else "Unknown"


async def sync_catalog(db: AsyncSession, handles: list[str] | None = None) -> dict:
    s = await get_settings(db)
    region = s.store_region or "au"
    handles = handles or s.store_handles or store.DEFAULT_HANDLES
    log_lines: list[str] = []
    stats = {"products": 0, "variants_new": 0, "variants_updated": 0, "missing": [], "spools_linked": 0}
    now = datetime.now(timezone.utc)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent": store.UA}) as client:
        discovered = await store.discover_handles(region, client)
        for h in discovered:
            if h not in handles:
                handles.append(h)
        for i, handle in enumerate(handles):
            if i:
                await asyncio.sleep(1.2)  # be polite; the store rate-limits bursts
            try:
                prod = await store.fetch_product(region, handle, client)
            except store.RateLimited:
                log_lines.append(f"{handle}: rate limited, giving up on this one")
                stats["missing"].append(handle)
                continue
            except Exception as e:
                log_lines.append(f"{handle}: error {e}")
                continue
            if prod is None or not prod.variants:
                stats["missing"].append(handle)
                log_lines.append(f"{handle}: not found / no variants")
                continue
            p = (await db.execute(select(FilamentProduct).where(FilamentProduct.name.ilike(prod.name)))).scalar_one_or_none()
            if p is None:
                p = (await db.execute(select(FilamentProduct).where(FilamentProduct.store_handle == handle))).scalar_one_or_none()
            if p is None:
                p = FilamentProduct(name=prod.name, material=material_from_name(prod.name), brand="Bambu Lab")
                db.add(p)
                await db.flush()
            p.store_handle = handle
            p.store_url = prod.url
            if prod.description and not p.description:
                p.description = prod.description
            p.last_synced_at = now
            stats["products"] += 1

            # Prefer "spool" variant images when both exist; colours are the unit.
            seen: dict[str, store.StoreVariant] = {}
            for v in prod.variants:
                cur = seen.get(v.colour_name)
                if cur is None or (cur.spool_type == "refill" and v.spool_type == "spool"):
                    seen[v.colour_name] = v
            for name, v in seen.items():
                row = (
                    await db.execute(select(FilamentVariant).where(FilamentVariant.product_id == p.id, FilamentVariant.colour_name == name))
                ).scalar_one_or_none()
                if row is None:
                    row = FilamentVariant(product_id=p.id, colour_name=name)
                    db.add(row)
                    stats["variants_new"] += 1
                else:
                    stats["variants_updated"] += 1
                row.colour_code = v.colour_code or row.colour_code
                row.image_url = v.image_url or row.image_url
                row.store_sku = v.sku
                row.store_price = v.price
                row.store_currency = v.currency
                row.store_url = v.url
                row.in_stock = v.in_stock
                row.last_synced_at = now
            log_lines.append(f"{handle}: {len(seen)} colours")
            await db.flush()

    # Link spools that have no variant yet, by product + colour name.
    spools = (await db.execute(select(Spool).where(Spool.variant_id.is_(None)))).scalars().all()
    for sp in spools:
        prod = (await db.execute(select(FilamentProduct).where(FilamentProduct.name.ilike(sp.subtype)))).scalar_one_or_none()
        if not prod:
            continue
        var = (
            await db.execute(
                select(FilamentVariant).where(FilamentVariant.product_id == prod.id, FilamentVariant.colour_name.ilike(sp.colour_name))
            )
        ).scalar_one_or_none()
        if var:
            sp.variant_id = var.id
            sp.product_id = prod.id
            if not sp.image_url:
                sp.image_url = var.image_url
            if not sp.colour_hex:
                sp.colour_hex = var.colour_hex
            stats["spools_linked"] += 1

    s.catalog_last_sync_at = now
    s.catalog_last_sync_log = "\n".join(log_lines)
    await db.commit()
    return stats
