"""First-run seed: product spec sheet + the spools from the original spreadsheet."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FilamentProduct, FilamentVariant, Spool, SpoolEvent
from .store import DEFAULT_HANDLES
from .inventory import get_settings

log = logging.getLogger("seed")

# name, material, handle, toughness, strength, stiffness, heat, dry_temp, dry_h, nozzle(min,max), bed(min,max), density
PRODUCTS = [
    ("PLA Basic", "PLA", "pla-basic-filament", 26.6, 76, 2750, 57, 50, 8, (190, 230), (35, 65), 1.24),
    ("PLA Matte", "PLA", "pla-matte", 26.6, 76, 2750, 57, 50, 8, (190, 230), (35, 65), 1.31),
    ("PLA Metal", "PLA", "pla-metal", 26.6, 76, 2750, 57, 50, 8, (190, 230), (35, 65), 1.24),
    ("PLA Silk Dual Color", "PLA", "pla-silk-multi-color", 26.6, 76, 2750, 57, 50, 8, (190, 230), (35, 65), 1.24),
    ("PLA Silk+", "PLA", "pla-silk-upgrade", 26.6, 76, 2750, 57, 50, 8, (190, 230), (35, 65), 1.24),
    ("PLA-CF", "PLA", "pla-cf", 23.2, 89, 3950, 55, 55, 8, (210, 240), (45, 65), 1.22),
    ("PETG HF", "PETG", "petg-hf", 31.5, 64, 2050, 69, 65, 8, (230, 260), (60, 80), 1.27),
    ("PETG Basic", "PETG", "petg-basic", 31.5, 64, 2050, 69, 65, 8, (230, 260), (60, 80), 1.27),
    ("TPU for AMS", "TPU", "tpu-for-ams", 124.3, None, None, None, 70, 8, (220, 240), (30, 35), 1.21),
    ("PAHT-CF", "PA", "paht-cf", 57.5, 125, 4230, 194, 80, 8, (260, 300), (100, 120), 1.22),
    ("PC", "PC", "pc-filament", 34.8, 108, 2310, 117, 80, 8, (260, 290), (90, 100), 1.20),
    ("ABS", "ABS", "abs-filament", 39.3, 61, 1970, 87, 80, 8, (240, 270), (90, 100), 1.04),
]

# subtype, colour, hex, spool_type, weight_g, opened, seed image
SPOOLS = [
    ("TPU for AMS", "Black", "000000", "spool", 1000, True, "cellImage_82830761_0.jpg"),
    ("TPU for AMS", "Neon Green", "8EFF1A", "spool", 1000, True, "cellImage_82830761_1.jpg"),
    ("PAHT-CF", "Black", "000000", "spool", 500, False, "cellImage_82830761_2.jpg"),
    ("PC", "Black", "000000", "spool", 1000, False, "cellImage_82830761_3.jpg"),
    ("PLA-CF", "Black", "000000", "spool", 1000, True, "cellImage_82830761_4.jpg"),
    ("PLA Basic", "Jade White", "FFFFFF", "spool", 1000, True, "cellImage_82830761_5.jpg"),
    ("PLA Basic", "Black", "000000", "spool", 1000, False, "cellImage_82830761_6.jpg"),
    ("PLA Basic", "Bambu Green", "00AE42", "spool", 1000, True, "cellImage_82830761_7.jpg"),
    ("PLA Matte", "Latte Brown", "D3B7A7", "refill", 1000, True, "cellImage_82830761_8.jpg"),
    ("PLA Matte", "Ice Blue", "A3D8E1", "refill", 1000, True, "cellImage_82830761_9.jpg"),
    ("PLA Metal", "Cobalt Blue Metallic", "39519A", "spool", 1000, False, "cellImage_82830761_10.jpg"),
    ("PLA Silk Dual Color", "Midnight Blaze (Blue-Red)", "5B2C8F", "spool", 1000, False, "cellImage_82830761_11.jpg"),
    ("PLA Silk Dual Color", "Blue Hawaii (Blue-Green)", "2F9FB0", "spool", 1000, True, "cellImage_82830761_12.jpg"),
    ("PETG HF", "Lime Green", "7DCE13", "refill", 1000, False, "cellImage_82830761_13.jpg"),
]


async def seed_if_empty(db: AsyncSession) -> bool:
    count = (await db.execute(select(func.count()).select_from(FilamentProduct))).scalar_one()
    if count:
        return False
    log.info("seeding products and spools")
    now = datetime.now(timezone.utc)
    products: dict[str, FilamentProduct] = {}
    for name, mat, handle, tough, strength, stiff, heat, dt, dh, nozzle, bed, dens in PRODUCTS:
        p = FilamentProduct(
            name=name, material=mat, store_handle=handle, brand="Bambu Lab",
            store_url=f"https://au.store.bambulab.com/products/{handle}",
            toughness_kj_m2=tough, strength_mpa=strength, stiffness_mpa=stiff, heat_resistance_c=heat,
            drying_temp_c=dt, drying_time_h=dh, nozzle_temp_min_c=nozzle[0], nozzle_temp_max_c=nozzle[1],
            bed_temp_min_c=bed[0], bed_temp_max_c=bed[1], density_g_cm3=dens,
        )
        db.add(p)
        products[name] = p
    await db.flush()

    for subtype, colour, hx, stype, weight, opened, img in SPOOLS:
        p = products[subtype]
        var = FilamentVariant(product_id=p.id, colour_name=colour, colour_hex=hx, image_url=f"/seed-images/{img}")
        db.add(var)
        await db.flush()
        sp = Spool(
            variant_id=var.id, product_id=p.id, brand="Bambu Lab", material=p.material, subtype=subtype,
            colour_name=colour, colour_hex=hx, image_url=f"/seed-images/{img}", spool_type=stype,
            starting_weight_g=weight, remaining_g=weight, location="stored", opened=opened,
            opened_at=now if opened else None, created_at=now,
            notes="Imported from spreadsheet. Remaining weight is a guess until the AMS sees it or you weigh it.",
        )
        db.add(sp)
        await db.flush()
        db.add(SpoolEvent(spool_id=sp.id, type="created", remaining_g=weight, source="seed", note="Imported from spreadsheet"))

    s = await get_settings(db)
    if not s.store_handles:
        s.store_handles = list(DEFAULT_HANDLES)
    await db.commit()
    return True
