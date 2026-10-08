"""The Eye on Methane (MARS) importer, against a fixture that follows the published columns.

The fixture's rows are invented (source ids TST…); they only exercise the column
mapping from https://methanedata.unep.org/dict-mars-plumes.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest

from geoapps_workers.steps.mars import read_records, to_detection

FIXTURE = Path(__file__).parent / "data" / "mars_fixture.csv"


def test_reads_csv_with_bom_and_normalizes_headers():
    rows = read_records(FIXTURE.read_bytes(), FIXTURE.name)
    assert len(rows) == 6
    assert "id_plume" in rows[0]  # the BOM is stripped from the first header


def test_reads_csv_inside_zip_and_skips_other_members():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "not data")
        z.writestr("other.csv", "a,b\n1,2\n")  # no id_plume column: ignored
        z.writestr("unep_methanedata_detected_plumes.csv", FIXTURE.read_bytes())
    assert len(read_records(buf.getvalue(), "plumes.zip")) == 6


def test_reads_geojson_points():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-103.48, 31.87]},
                "properties": {
                    "id_plume": "g1",
                    "tile_date": "2025-05-01T00:00:00Z",
                    "ch4_fluxrate": 800,
                },
            }
        ],
    }
    (rec,) = read_records(json.dumps(fc).encode(), "plumes.geojson")
    assert (rec["lon"], rec["lat"]) == (-103.48, 31.87)


def test_mapping_of_one_record():
    rows = read_records(FIXTURE.read_bytes(), FIXTURE.name)
    d = to_detection(rows[0], p_assumed=0.95)
    assert d["record_id"] == "fixture-0001" and d["source_name"] == "TST001"
    assert d["sensor"] == "Sentinel-2 (ESA)" and d["scene_id"] == "S2A_FIXTURE_20250501"
    assert d["marks"] == {
        "p": 0.95,
        "q_kg_h": 1200.0,
        "q_sigma_kg_h": 400.0,
        "wind_u_m_s": 3.1,
        "wind_v_m_s": 0.4,
        "wind_speed_m_s": 3.13,
    }
    assert d["attrs"]["notified"] is True and d["attrs"]["actionable"] == "Yes"
    assert d["observed_at"].isoformat() == "2025-05-01T17:20:00+00:00"
    # an unquantified plume keeps no flux rather than a zero
    assert "q_kg_h" not in to_detection(rows[3], 0.95)["marks"]
    for bad, msg in ((rows[4], "lat/lon"), (rows[5], "tile_date")):
        with pytest.raises(ValueError, match=msg):
            to_detection(bad, 0.95)
