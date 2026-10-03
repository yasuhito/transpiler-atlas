import copy
import json
import shutil

import pytest

import atlas
import build_site


def test_overlay_preserves_campaign_and_is_idempotent():
    raw = json.loads((atlas.ROOT / "data/results.json").read_text())
    original = copy.deepcopy(raw)
    display, notes = build_site.display_data(raw)
    assert raw == original
    assert build_site.display_data(display) == (display, notes)
    assert json.loads(json.dumps(notes)) == notes
    assert notes["suite"] == "pilot-v0.4"
    assert notes["score_version"] == "qcec-adjusted-v1"
    assert {c["id"] for c in notes["protocol"]["configurations"]} == set(
        atlas.CONFIGURATION_ANNOTATIONS
    )
    expected = copy.deepcopy(raw)
    expected["score_version"] = build_site.SCORE_VERSION
    for row in expected["results"]:
        for trial in row.get("trials", []):
            trial["validation"].pop("details", None)
    assert display["results"] == expected["results"]
    for c in expected["protocol"]["configurations"]:
        c.update(atlas.CONFIGURATION_ANNOTATIONS.get(c["id"], {}))
    assert display == expected


@pytest.mark.parametrize("fault", ["unknown", "override", "duplicate", "type"])
def test_overlay_rejects_unsafe_metadata(fault):
    raw = json.loads((atlas.ROOT / "data/results.json").read_text())
    notes = atlas.configuration_annotations()
    if fault == "unknown":
        notes["unknown"] = notes.pop("bqskit-l2")
    elif fault == "override":
        notes["bqskit-l2"]["optimization_level"] = 1
    elif fault == "duplicate":
        raw["protocol"]["configurations"].append(raw["protocol"]["configurations"][0])
    else:
        notes["bqskit-l2"]["numerical_approximation"] = "true"
    with pytest.raises(ValueError):
        build_site.display_data(raw, notes)


def test_legacy_missing_metadata_and_build_byte_preservation(tmp_path, monkeypatch):
    for release in ("pilot-v0.1", "pilot-v0.2", "pilot-v0.3"):
        raw = json.loads((atlas.ROOT / "releases" / release / "data/results.json").read_text())
        # Earlier releases lack this explanatory metadata, regardless of registry shape.
        display, notes = build_site.display_data(raw, {})
        assert not notes["protocol"]["configurations"]
        assert all(
            "numerical_approximation" not in c
            for c in display["protocol"].get("configurations", [])
        )
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    shutil.copytree(atlas.ROOT / "web", tmp_path / "web")
    shutil.copy(atlas.ROOT / "data/results.json", tmp_path / "data/results.json")
    original = (tmp_path / "data/results.json").read_bytes()
    monkeypatch.setattr(build_site, "ROOT", tmp_path)
    build_site.build()
    assert (tmp_path / "data/results.json").read_bytes() == original
    assert json.loads((tmp_path / "data/configuration-notes.json").read_text())["protocol"][
        "configurations"
    ]
    first = (tmp_path / "index.html").read_bytes()
    build_site.build()
    assert (tmp_path / "index.html").read_bytes() == first
