"""SQLAlchemy models. See docs/DESIGN.md §3."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FilamentProduct(Base):
    """A Bambu product line (e.g. PLA Basic). Holds the spec sheet."""

    __tablename__ = "filament_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand: Mapped[str] = mapped_column(String(64), default="Bambu Lab")
    material: Mapped[str] = mapped_column(String(32))  # PLA, PETG, TPU, PC, PA...
    name: Mapped[str] = mapped_column(String(96), unique=True)  # "PLA Basic"
    store_handle: Mapped[str | None] = mapped_column(String(96))
    store_url: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    toughness_kj_m2: Mapped[float | None] = mapped_column(Float)
    strength_mpa: Mapped[float | None] = mapped_column(Float)
    stiffness_mpa: Mapped[float | None] = mapped_column(Float)
    heat_resistance_c: Mapped[float | None] = mapped_column(Float)
    drying_temp_c: Mapped[float | None] = mapped_column(Float)
    drying_time_h: Mapped[float | None] = mapped_column(Float)
    nozzle_temp_min_c: Mapped[int | None] = mapped_column(Integer)
    nozzle_temp_max_c: Mapped[int | None] = mapped_column(Integer)
    bed_temp_min_c: Mapped[int | None] = mapped_column(Integer)
    bed_temp_max_c: Mapped[int | None] = mapped_column(Integer)
    density_g_cm3: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    variants: Mapped[list[FilamentVariant]] = relationship(back_populates="product", cascade="all, delete-orphan")

    @property
    def shrinkage_rank(self) -> float | None:
        """Print-shrinkage rank, 1 (least) .. 7 (most). Derived from material, not stored."""
        return shrinkage_rank(self.material, self.name)


# Bambu wiki "3D Prints Shrinkage" ordering of base polymers, most -> least shrink-prone:
# PC > PA > ABS > ASA > PETG > PLA. Fibre-filled (CF/GF) variants shrink a little less
# than the base polymer, so they get a -0.5 nudge (a hint, not a measurement).
SHRINKAGE_RANK = {"PLA": 1, "PETG": 2, "PET": 2, "ASA": 3, "ABS": 4, "PA": 5, "PC": 7}
FIBRE_BONUS = 0.5


def shrinkage_rank(material: str | None, name: str | None = None) -> float | None:
    base = SHRINKAGE_RANK.get((material or "").upper())
    if base is None:
        return None
    n = (name or "").upper().replace("-", " ").replace("_", " ")
    fibre = any(tok in ("CF", "GF") for tok in n.split())
    return base - FIBRE_BONUS if fibre else base


class FilamentVariant(Base):
    """One colour of a product, as listed on the Bambu store."""

    __tablename__ = "filament_variants"
    __table_args__ = (UniqueConstraint("product_id", "colour_name", name="uq_variant_colour"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("filament_products.id", ondelete="CASCADE"))
    colour_name: Mapped[str] = mapped_column(String(96))
    colour_code: Mapped[str | None] = mapped_column(String(16))  # Bambu "10100"
    colour_hex: Mapped[str | None] = mapped_column(String(16))
    image_url: Mapped[str | None] = mapped_column(String(512))
    store_sku: Mapped[str | None] = mapped_column(String(64))
    store_price: Mapped[float | None] = mapped_column(Float)
    store_currency: Mapped[str | None] = mapped_column(String(8))
    store_url: Mapped[str | None] = mapped_column(String(512))
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[FilamentProduct] = relationship(back_populates="variants")


class Spool(Base):
    """A physical spool you own. THE inventory item."""

    __tablename__ = "spools"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("filament_variants.id", ondelete="SET NULL"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("filament_products.id", ondelete="SET NULL"))
    tray_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    tag_uid: Mapped[str | None] = mapped_column(String(64))

    brand: Mapped[str] = mapped_column(String(64), default="Bambu Lab")
    material: Mapped[str] = mapped_column(String(32))
    subtype: Mapped[str] = mapped_column(String(96))  # "PLA Basic"
    colour_name: Mapped[str] = mapped_column(String(96))
    colour_hex: Mapped[str | None] = mapped_column(String(16))
    image_url: Mapped[str | None] = mapped_column(String(512))
    spool_type: Mapped[str] = mapped_column(String(16), default="spool")  # spool | refill

    starting_weight_g: Mapped[float] = mapped_column(Float, default=1000.0)
    remaining_g: Mapped[float] = mapped_column(Float, default=1000.0)
    ams_remaining_pct: Mapped[int | None] = mapped_column(Integer)
    ams_divergent: Mapped[bool] = mapped_column(Boolean, default=False)

    location: Mapped[str] = mapped_column(String(32), default="stored")  # stored|ams:0..3|external|discarded
    opened: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    variant: Mapped[FilamentVariant | None] = relationship()
    product: Mapped[FilamentProduct | None] = relationship()
    events: Mapped[list[SpoolEvent]] = relationship(
        back_populates="spool", cascade="all, delete-orphan", order_by="SpoolEvent.created_at.desc()"
    )

    @property
    def remaining_pct(self) -> float:
        if not self.starting_weight_g:
            return 0.0
        return max(0.0, min(100.0, self.remaining_g / self.starting_weight_g * 100))


class AmsSlot(Base):
    __tablename__ = "ams_slots"

    slot_index: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0..3
    spool_id: Mapped[int | None] = mapped_column(ForeignKey("spools.id", ondelete="SET NULL"))
    present: Mapped[bool] = mapped_column(Boolean, default=False)
    tray_uuid: Mapped[str | None] = mapped_column(String(64))
    tag_uid: Mapped[str | None] = mapped_column(String(64))
    tray_type: Mapped[str | None] = mapped_column(String(32))
    tray_sub_brands: Mapped[str | None] = mapped_column(String(96))
    tray_color: Mapped[str | None] = mapped_column(String(16))
    tray_weight: Mapped[float | None] = mapped_column(Float)
    remain_pct: Mapped[int | None] = mapped_column(Integer)
    nozzle_temp_min: Mapped[int | None] = mapped_column(Integer)
    nozzle_temp_max: Mapped[int | None] = mapped_column(Integer)
    needs_identification: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)  # tray_now
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    spool: Mapped[Spool | None] = relationship()

    @property
    def label(self) -> str:
        return f"A{self.slot_index + 1}"


class Print(Base):
    __tablename__ = "prints"

    id: Mapped[int] = mapped_column(primary_key=True)
    subtask_name: Mapped[str] = mapped_column(String(255))
    gcode_file: Mapped[str | None] = mapped_column(String(255))
    plate_index: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|finished|failed|unresolved|resolved
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    planned_total_g: Mapped[float | None] = mapped_column(Float)
    three_mf_fetched: Mapped[bool] = mapped_column(Boolean, default=False)
    fetch_error: Mapped[str | None] = mapped_column(Text)
    slot_snapshot: Mapped[dict | None] = mapped_column(JSON)  # {slot_index: spool_id}

    usage: Mapped[list[PrintFilamentUsage]] = relationship(back_populates="print", cascade="all, delete-orphan")


class PrintFilamentUsage(Base):
    __tablename__ = "print_filament_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    print_id: Mapped[int] = mapped_column(ForeignKey("prints.id", ondelete="CASCADE"))
    filament_index: Mapped[int] = mapped_column(Integer)  # slicer filament id (1-based)
    tray_index: Mapped[int | None] = mapped_column(Integer)  # AMS slot 0..3
    spool_id: Mapped[int | None] = mapped_column(ForeignKey("spools.id", ondelete="SET NULL"))
    filament_type: Mapped[str | None] = mapped_column(String(32))
    colour_hex: Mapped[str | None] = mapped_column(String(16))
    planned_g: Mapped[float] = mapped_column(Float, default=0)
    planned_m: Mapped[float | None] = mapped_column(Float)
    applied_g: Mapped[float | None] = mapped_column(Float)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    print: Mapped[Print] = relationship(back_populates="usage")
    spool: Mapped[Spool | None] = relationship()


class SpoolEvent(Base):
    __tablename__ = "spool_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    spool_id: Mapped[int] = mapped_column(ForeignKey("spools.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    delta_g: Mapped[float | None] = mapped_column(Float)
    remaining_g: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="user")  # user|ams|print|seed|system
    note: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    spool: Mapped[Spool] = relationship(back_populates="events")


class AppSettings(Base):
    """Single-row table (id=1)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    printer_mode: Mapped[str] = mapped_column(String(8), default="mock")  # mock|live|off
    printer_host: Mapped[str] = mapped_column(String(128), default="")
    printer_serial: Mapped[str] = mapped_column(String(64), default="")
    printer_access_code: Mapped[str] = mapped_column(String(64), default="")
    low_pct: Mapped[int] = mapped_column(Integer, default=20)
    low_g: Mapped[int] = mapped_column(Integer, default=150)
    divergence_pct: Mapped[int] = mapped_column(Integer, default=15)
    store_region: Mapped[str] = mapped_column(String(8), default="au")
    store_handles: Mapped[list] = mapped_column(JSON, default=list)
    catalog_last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    catalog_last_sync_log: Mapped[str | None] = mapped_column(Text)
