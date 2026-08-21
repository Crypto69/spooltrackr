import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings as env
from .db import Base, SessionLocal, engine
from .printer.manager import PrinterManager
from .routers.api import router
from .services.inventory import InventoryService, get_settings
from .services.seed import seed_if_empty

logging.basicConfig(level=env.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")


async def _wait_for_db(retries: int = 30) -> None:
    for i in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as e:
            log.warning("database not ready (%s), retrying...", type(e).__name__)
            await asyncio.sleep(2)
    raise RuntimeError("database never became ready")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _wait_for_db()
    async with SessionLocal() as db:
        seeded = await seed_if_empty(db)
        s = await get_settings(db)
        # First boot: take printer settings from env so docker-compose can pre-fill them.
        if seeded or (not s.printer_host and env.printer_host):
            s.printer_mode = env.printer_mode if (env.printer_host or env.printer_mode != "live") else s.printer_mode
            s.printer_host = s.printer_host or env.printer_host
            s.printer_serial = s.printer_serial or env.printer_serial
            s.printer_access_code = s.printer_access_code or env.printer_access_code
        await db.commit()
        cfg = (s.printer_mode, s.printer_host, s.printer_serial, s.printer_access_code)

    inventory = InventoryService(SessionLocal, lambda: app.state.printer.link)
    manager = PrinterManager(inventory)
    app.state.inventory = inventory
    app.state.printer = manager
    await manager.configure(*cfg)
    yield
    await manager.stop()
    await engine.dispose()


app = FastAPI(title="SpoolTrackr", lifespan=lifespan)
app.include_router(router)

app.mount("/seed-images", StaticFiles(directory=str(env.seed_dir / "images")), name="seed-images")

if env.frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(env.frontend_dist / "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        target = env.frontend_dist / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(env.frontend_dist / "index.html")
