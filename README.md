# SpoolTrackr

Filament inventory for a Bambu Lab X1C + AMS. Every spool you own, how much
is left on it, its specs, and what is in the printer right now — kept up to
date automatically from the printer over your LAN.

* **Inventory** — all spools, pictures, remaining grams/%, low-filament badges, filters.
* **AMS** — the four slots live. Bambu RFID spools are recognised automatically;
  unknown or third-party spools get a "Which spool is this?" prompt.
* **Prints** — each job's filament use is read from the sliced `.3mf` on the
  printer and deducted from the right spools when the print finishes. Stopped
  prints wait for you to pick how much to deduct.
* **Catalog** — Bambu product lines with spec sheets (temps, strength, drying…)
  and every colour/picture/price pulled from the Bambu store.
* **Settings** — printer connection, low thresholds, store region.

Stack: Vue 3 + Pinia · FastAPI (Python 3.12) · PostgreSQL 16 · MQTT/FTPS to the
printer · Docker. Design notes in [`docs/DESIGN.md`](docs/DESIGN.md).

## Run it locally (dev)

```bash
# database
docker run -d --name spooltrackr-dev-pg -e POSTGRES_USER=spool -e POSTGRES_PASSWORD=spool \
  -e POSTGRES_DB=spooltrackr -p 5433:5432 postgres:16-alpine

# backend (serves the API; also serves frontend/dist if it exists)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend with hot reload (proxies /api to :8000)
cd frontend && npm install && npm run dev     # http://localhost:5173
```

First boot seeds the catalog and the 14 spools from the original spreadsheet,
and starts a **mock printer** so everything works without hardware. Switch to
**Live** in Settings and enter the printer's IP, serial and LAN access code.

## Tests

```bash
cd backend && .venv/bin/python -m pytest          # parsers + end-to-end flow (needs the dev Postgres)
cd frontend && npm run build && npx playwright test   # browser tests against a running backend (fresh DB, mock mode)
```

## Deploy on the NAS

Single `docker compose` stack; pick a free LAN port (default 8322).

```bash
ssh <nas>
cd <apps-folder>
git clone https://github.com/Crypto69/spooltrackr.git && cd spooltrackr
chmod -R a+rX .
cp .env.example .env && vi .env      # printer IP / serial / access code, db password
./deploy.sh
```

Then open `http://<nas>:8322`. Postgres data lives in `./data/pg`.
Updates: `./deploy.sh` (pulls `main` first; `./deploy.sh --no-pull` to skip).

## Printer requirements

* X1C on the same LAN, ideally with a fixed IP.
* Printer screen → Settings → Network: IP address and **Access Code**.
* Firmware 01.08+: enable **Developer Mode** so LAN MQTT/FTP are allowed
  (cloud binding can stay on).
* The app connects to MQTT (`8883`, user `bblp`) and FTPS (`990`) using the access code.

## How remaining weight is estimated

`remaining = starting weight − Σ slicer used_g of finished prints ± manual corrections`.
The AMS's own % estimate is shown alongside and you get a warning (and a
one-click "use AMS" button) when the two disagree by more than the threshold.
Purge, prime towers and failed prints are not exact — weigh a spool now and
then and hit **Adjust weight**.
