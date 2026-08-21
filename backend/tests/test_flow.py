"""End-to-end: seeded inventory + mock AMS + a print, through the HTTP API."""
import asyncio


async def wait_until(fn, timeout=3.0):
    for _ in range(int(timeout / 0.05)):
        if await fn():
            return True
        await asyncio.sleep(0.05)
    return False


async def test_seed_and_mock_ams(client):
    spools = (await client.get("/api/spools")).json()
    assert len(spools) == 14  # spreadsheet rows
    slots = (await client.get("/api/ams")).json()
    # Seeded spools have no RFID yet -> app asks instead of duplicating
    assert slots[0]["needs_identification"] is True and slots[0]["spool"] is None
    cands = (await client.get("/api/ams/0/candidates")).json()
    assert [c["colour_name"] for c in cands["best"]] == ["Jade White"]

    # Identify A1 as the seeded Jade White -> claims the RFID id
    jade = cands["best"][0]["id"]
    r = await client.post("/api/ams/0/assign", json={"spool_id": jade})
    assert r.status_code == 200
    s = (await client.get(f"/api/spools/{jade}")).json()
    assert s["location"] == "ams:0" and s["tray_uuid"] == "FB9363D5A52340FB82E133A8CBDBFC31"
    assert s["ams_remaining_pct"] == 82
    assert len((await client.get("/api/spools")).json()) == 14  # no duplicate created

    # Third-party PETG in A4 needs identification; create a spool for it
    assert slots[3]["needs_identification"] is True
    r = await client.post("/api/ams/3/assign", json={"create": {"brand": "eSUN", "material": "PETG", "subtype": "PETG", "colour_name": "Orange", "starting_weight_g": 1000}})
    esun = r.json()[3]["spool"]
    assert esun["brand"] == "eSUN" and esun["colour_hex"] == "FF6600"


async def test_print_deducts_from_right_spools(client):
    cands = (await client.get("/api/ams/0/candidates")).json()
    jade = cands["best"][0]["id"]
    await client.post("/api/ams/0/assign", json={"spool_id": jade})
    cands2 = (await client.get("/api/ams/1/candidates")).json()
    black = cands2["best"][0]["id"]
    await client.post("/api/ams/1/assign", json={"spool_id": black})

    r = await client.post("/api/debug/mock/start", json={"name": "bracket", "filaments": [
        {"type": "PLA", "color": "FFFFFF", "used_g": 40.0}, {"type": "PLA", "color": "000000", "used_g": 10.5}]})
    assert r.status_code == 200

    async def started():
        st = (await client.get("/api/state")).json()
        return st["active_print"] is not None
    assert await wait_until(started)
    prints = (await client.get("/api/prints")).json()
    assert prints[0]["three_mf_fetched"] and prints[0]["planned_total_g"] == 50.5
    by_spool = {u["spool_id"]: u["planned_g"] for u in prints[0]["usage"]}
    assert by_spool == {jade: 40.0, black: 10.5}

    await client.post("/api/debug/mock/finish", json={})

    async def finished():
        return (await client.get("/api/prints")).json()[0]["status"] == "finished"
    assert await wait_until(finished)
    j = (await client.get(f"/api/spools/{jade}")).json()
    b = (await client.get(f"/api/spools/{black}")).json()
    assert j["remaining_g"] == 960.0 and b["remaining_g"] == 989.5
    assert j["events"][0]["type"] == "print_usage" and j["events"][0]["delta_g"] == -40.0
    assert j["total_used_g"] == 40.0


async def test_failed_print_is_unresolved_then_resolved(client):
    cands = (await client.get("/api/ams/0/candidates")).json()
    jade = cands["best"][0]["id"]
    await client.post("/api/ams/0/assign", json={"spool_id": jade})
    await client.post("/api/debug/mock/start", json={"name": "vase", "filaments": [{"type": "PLA", "color": "FFFFFF", "used_g": 100.0}]})
    await client.post("/api/debug/mock/progress", json={"pct": 40})
    await client.post("/api/debug/mock/fail", json={})

    async def unresolved():
        ps = (await client.get("/api/prints")).json()
        return ps and ps[0]["status"] == "unresolved"
    assert await wait_until(unresolved)
    p = (await client.get("/api/prints")).json()[0]
    assert p["progress_pct"] == 40
    assert (await client.get(f"/api/spools/{jade}")).json()["remaining_g"] == 1000.0
    r = await client.post(f"/api/prints/{p['id']}/resolve", json={"fraction": 0.4})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert (await client.get(f"/api/spools/{jade}")).json()["remaining_g"] == 960.0


async def test_unload_and_reload_keeps_estimate(client):
    cands = (await client.get("/api/ams/0/candidates")).json()
    jade = cands["best"][0]["id"]
    await client.post("/api/ams/0/assign", json={"spool_id": jade})
    await client.post(f"/api/spools/{jade}/adjust", json={"remaining_g": 700, "note": "weighed"})
    await client.post("/api/debug/mock/unload", json={"slot": 0})

    async def stored():
        return (await client.get(f"/api/spools/{jade}")).json()["location"] == "stored"
    assert await wait_until(stored)
    # reinsert in a different slot: recognised by RFID, no prompt, estimate kept
    await client.post("/api/debug/mock/load", json={"slot": 2, "tray_uuid": "FB9363D5A52340FB82E133A8CBDBFC31", "sub_brands": "PLA Basic", "colour": "FFFFFFFF", "remain": 70})

    async def moved():
        return (await client.get(f"/api/spools/{jade}")).json()["location"] == "ams:2"
    assert await wait_until(moved)
    s = (await client.get(f"/api/spools/{jade}")).json()
    assert s["remaining_g"] == 700 and s["ams_remaining_pct"] == 70 and not s["ams_divergent"]
    assert [e["type"] for e in s["events"][:3]] == ["loaded", "unloaded", "manual_adjustment"]
    slots = (await client.get("/api/ams")).json()
    assert slots[2]["spool"]["id"] == jade and slots[2]["needs_identification"] is False


async def test_refill_and_discard(client):
    spools = (await client.get("/api/spools")).json()
    sp = spools[0]
    r = await client.post(f"/api/spools/{sp['id']}/refill", json={"subtype": "PLA Basic", "colour_name": "Red", "colour_hex": "#C12E1F", "starting_weight_g": 1000})
    assert r.json()["colour_name"] == "Red" and r.json()["remaining_g"] == 1000 and r.json()["colour_hex"] == "C12E1F"
    r = await client.post(f"/api/spools/{sp['id']}/discard")
    assert r.json()["location"] == "discarded"
    assert all(s["id"] != sp["id"] for s in (await client.get("/api/spools")).json())


async def test_spools_include_product_specs(client):
    spools = (await client.get("/api/spools")).json()
    by_sub = {s["subtype"]: s for s in spools}
    assert by_sub["PAHT-CF"]["strength_mpa"] == 125 and by_sub["PAHT-CF"]["heat_resistance_c"] == 194
    assert by_sub["PLA Basic"]["strength_mpa"] == 76
    assert by_sub["PLA-CF"]["stiffness_mpa"] == 3950 and by_sub["PLA-CF"]["toughness_kj_m2"] == 23.2
    assert by_sub["TPU for AMS"]["strength_mpa"] is None  # no spec on the sheet
    one = (await client.get(f"/api/spools/{by_sub['PC']['id']}")).json()
    assert one["heat_resistance_c"] == 117
