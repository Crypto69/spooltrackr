# SpoolTrackr — High-Level Design

Personal filament inventory for a Bambu Lab X1C + AMS. Runs as one Docker
stack on the TerraMaster NAS. No login.

Core principle (from the original input doc): **the AMS is not the
inventory — the spool is.** The AMS is a temporary *location* and a sensor.

## 1. Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Vue 3 + Vite + Pinia + vue-router | Requested; palette borrowed from stl2prism |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg | Matches the NAS deploy pattern already proven (uvicorn serving built Vue as static files) |
| Printer link | paho-mqtt (TLS, port 8883) + implicit FTPS (port 990) | That is how the X1C exposes AMS state and the sliced `.gcode.3mf` |
| Database | PostgreSQL 16 (separate container, bind-mounted volume) | Requested |
| Live updates | Server-Sent Events at `/api/events` | One-way push is all we need; simpler than websockets |
| Deploy | `docker compose` on the NAS, LAN port **8322** | Next free port per `nas-deployment-guide.md` |

## 2. Components

```
X1C ──MQTT 8883──▶ PrinterLink ──▶ InventoryService ──▶ PostgreSQL
     ◀─FTPS 990──┘   (backend/app/printer/*)     │
                                                  ▼
                               FastAPI /api/*  ──SSE──▶ Vue UI
Bambu store ──HTTPS──▶ CatalogSync (parses schema.org JSON-LD in product pages)
```

* **PrinterLink** — connects to the printer, sends `pushall`, parses every
  `report` message. Emits normalised events: `ams_snapshot`,
  `print_started`, `print_finished`, `print_failed`, `progress`.
  Has a **mock** implementation (`PRINTER_MODE=mock`) that fakes an AMS and
  prints so the UI can be developed and Playwright-tested with no printer.
* **InventoryService** — the only thing that mutates spools. Handles:
  recognise spool by `tray_uuid`; load/unload events; unknown-spool
  prompts; print-usage deduction from `slice_info.config`; manual
  adjustments; refills; AMS-vs-calculated divergence warnings.
* **CatalogSync** — Bambu's store is Next.js (not Shopify JSON). Every
  product page embeds a `schema.org/ProductGroup` JSON-LD listing each
  variant as `"<Product> - <Colour> (<colour code>) / <Refill|Filament with spool> / <size>"`
  with an image URL and price. We fetch a configurable list of product
  handles, parse that block, and upsert `filament_variants`. Mechanical
  specs (strength, temps…) are *not* machine-readable on the store, so they
  live in `filament_products` seeded from the spreadsheet and editable in the UI.

## 3. Data model

```
filament_products   one row per Bambu product line (PLA Basic, PETG HF …)
  id, brand, material (PLA/PETG/TPU…), name, store_handle,
  toughness_kj_m2, strength_mpa, stiffness_mpa, heat_resistance_c,
  drying_temp_c, drying_time_h, nozzle_temp_min/max_c, bed_temp_min/max_c,
  density_g_cm3, notes

filament_variants   one row per colour of a product
  id, product_id, colour_name, colour_code (Bambu "10100"), colour_hex,
  image_url, store_sku, store_price, store_url, last_synced_at

spools              physical spool you own  (THE inventory)
  id, variant_id?, product_id?, tray_uuid?, tag_uid?,
  brand, material, subtype, colour_name, colour_hex, image_url,
  spool_type (spool|refill), starting_weight_g, remaining_g,
  ams_remaining_pct?, location (stored|ams:A1..A4|external|discarded),
  opened, purchased_at?, opened_at?, created_at, last_seen_at?, notes

ams_slots           A1..A4 live mapping
  slot_index (0..3), label, spool_id?, tray_uuid?, tray_type,
  tray_sub_brands, tray_color, remain_pct, tray_weight, updated_at,
  needs_identification (true when tray present but no matched spool)

prints              one per job seen via MQTT
  id, subtask_name, gcode_file, started_at, ended_at, status
  (running|finished|failed|cancelled|unresolved), progress_pct,
  planned_total_g, three_mf_fetched

print_filament_usage
  id, print_id, filament_index, tray_index?, spool_id?, filament_type,
  colour_hex, planned_g, planned_m, applied_g, applied_at

spool_events        append-only history
  id, spool_id, type (created|loaded|unloaded|print_usage|manual_adjustment|
  ams_reconciliation|refill|discarded), delta_g, remaining_g, source,
  created_at, meta (jsonb)

settings            single row: printer_host, printer_serial, access_code,
                    printer_mode (live|mock), low_pct, low_g, store_region,
                    store_handles[]
```

## 4. Key flows

**AMS snapshot** (every report with `ams` data):
1. For each tray: if `tray_uuid` is set and non-zero → find spool by uuid.
   Found → set `location=ams:An`, `ams_remaining_pct`, `last_seen_at`;
   emit `loaded` event if location changed.
   Not found → auto-create a spool from the tray data (Bambu RFID), mark
   `created` with `source=ams`.
2. Tray present but no uuid (third-party) → mark slot
   `needs_identification`; UI offers "Which spool is this?" picker.
3. Slots whose previous spool is gone → `unloaded` event, `location=stored`.
4. If AMS % and calculated % differ by > 15 points → flag on spool.

**Print lifecycle**:
1. `gcode_state` goes to `RUNNING` with a new `subtask_name` → create
   `prints` row, snapshot slot→spool mapping, fetch `.3mf` over FTPS
   (`/cache/<subtask>.3mf` etc.), parse `Metadata/slice_info.config`
   for the active plate → `print_filament_usage` rows with `planned_g`.
   Filament index → spool uses `ams_mapping` when present, else type+colour
   match against loaded trays, else `tray_now`.
2. `FINISH` → apply `planned_g` to each spool (`print_usage` event).
3. `FAILED` / cancelled → mark `unresolved`, apply nothing; UI lets you
   apply a percentage (defaults to `mc_percent` at failure).

**Catalog sync**: `POST /api/catalog/sync` → for each handle fetch
`https://<region>.store.bambulab.com/products/<handle>`, parse JSON-LD,
upsert product + variants. Spools with a `variant_id` inherit image/hex.

## 5. API (all under `/api`)

```
GET  /version                       build sha/time
GET  /events                        SSE: ams, print, spool, slot events
GET  /state                         full snapshot (slots, printer, active print)
GET  /spools?location=&material=&low=1     list
POST /spools                        create (manual / third-party)
GET  /spools/{id}                   detail + events + usage
PATCH /spools/{id}                  edit fields
POST /spools/{id}/adjust            {remaining_g|delta_g, note}
POST /spools/{id}/refill            {variant_id?, starting_weight_g, ...}
POST /spools/{id}/discard
GET  /ams                           4 slots
POST /ams/{slot}/assign             {spool_id | create:{...}}
GET  /prints, GET /prints/{id}, POST /prints/{id}/resolve {fraction}
GET  /catalog/products, /catalog/variants?product_id=
POST /catalog/sync                  pull from store
GET/PUT /settings
POST /debug/mock/{action}           only in mock mode (load, unload, start, finish…)
```

## 6. Frontend screens

Inventory (card grid, filters, low-filament badges) · AMS (4 live slots,
identify-unknown prompt) · Spool detail (gauge, specs, history, adjust /
refill) · Prints (history, unresolved prints) · Catalog (products + colours,
sync button) · Settings (printer connection, thresholds, store handles).

## 7. Deployment

`docker-compose.yml`: `app` (this image, port 8322→8000, `mem_limit: 1g`)
+ `db` (postgres:16-alpine, volume `./data/pg`, `mem_limit: 512m`).
`deploy.sh` per the NAS guide. Images always built on the NAS.

## 8. Out of scope for v1

Multiple printers, QR/NFC labels, cloud sync, notifications, analytics.
