from pathlib import Path

from app.printer.bambu import parse_ams, parse_print
from app.printer.mock import _build_fake_3mf
from app.services import store, threemf

HERE = Path(__file__).parent


def test_parse_store_product_page():
    html = (HERE / "fixtures_pla_basic.html").read_text(encoding="utf-8")
    p = store.parse_product_html(html, "pla-basic-filament", "https://au.store.bambulab.com/products/pla-basic-filament")
    assert p is not None
    assert p.name == "PLA Basic"
    assert len(p.variants) >= 40
    jade = [v for v in p.variants if v.colour_name == "Jade White"]
    assert jade and jade[0].colour_code == "10100"
    assert {v.spool_type for v in jade} == {"spool", "refill"}
    assert all(v.image_url and v.image_url.startswith("https://") for v in p.variants)
    assert all(v.currency == "AUD" for v in p.variants)


def test_variant_name_regex_without_code():
    m = store.NAME_RE.match("PLA Silk Dual Color - Midnight Blaze (Blue-Red) / Filament with spool / 1 kg")
    assert m
    assert m.group("colour") == "Midnight Blaze (Blue-Red)"
    assert m.group("code") is None


def test_parse_3mf_usage():
    data = _build_fake_3mf([{"type": "PLA", "color": "FFFFFF", "used_g": 54.31, "used_m": 18.42}, {"type": "PETG", "color": "FF6600", "used_g": 6.1}])
    plates = threemf.parse_3mf(data)
    assert len(plates) == 1
    plate = threemf.pick_plate(plates, threemf.plate_index_from_gcode_file("/data/Metadata/plate_1.gcode"))
    assert plate.plate_index == 1
    assert [f.filament_index for f in plate.filaments] == [1, 2]
    assert plate.filaments[0].colour_hex == "FFFFFF"
    assert abs(plate.total_g - 60.41) < 0.001


def test_parse_ams_report():
    state = {
        "ams": {
            "tray_now": "1",
            "ams": [
                {
                    "id": "0",
                    "tray": [
                        {"id": "0", "tray_type": "PLA", "tray_sub_brands": "PLA Basic", "tray_color": "FFFFFFFF", "tray_uuid": "FB9363D5A52340FB82E133A8CBDBFC31", "tag_uid": "0000000000000001", "tray_weight": "1000", "remain": 82, "nozzle_temp_min": "190", "nozzle_temp_max": "230"},
                        {"id": "1", "tray_type": "PETG", "tray_sub_brands": "", "tray_color": "FF6600FF", "tray_uuid": "00000000000000000000000000000000", "tag_uid": "0000000000000000", "tray_weight": "0", "remain": -1},
                        {"id": "2"},
                        {"id": "3", "tray_type": ""},
                    ],
                }
            ],
        }
    }
    snap = parse_ams(state)
    assert snap.active_tray == 1
    t0, t1, t2, t3 = snap.trays
    assert t0.present and t0.tray_uuid == "FB9363D5A52340FB82E133A8CBDBFC31" and t0.remain_pct == 82
    assert t1.present and t1.tray_uuid is None and t1.tag_uid is None  # third party
    assert not t2.present and not t3.present


def test_parse_print_report():
    ps = parse_print({"gcode_state": "RUNNING", "subtask_name": "bracket", "gcode_file": "/data/Metadata/plate_2.gcode", "mc_percent": 37, "ams_mapping": [0, 2]})
    assert ps.gcode_state == "RUNNING" and ps.progress_pct == 37 and ps.ams_mapping == [0, 2]
    assert threemf.plate_index_from_gcode_file(ps.gcode_file) == 2
    assert parse_print({}) is None
