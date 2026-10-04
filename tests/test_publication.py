import json
import shutil

import pytest
from publication_fixtures import qmap_publication_map
from test_campaign import synthetic_document

import atlas
import campaign
import publication


def assert_publication(root, *, file_map=None):
    data, raw_path = publication.load(root, file_map=file_map)
    mapping_name = file_map or json.loads((root / "publication.json").read_text())["file_map"]
    mapping = json.loads((root / mapping_name).read_text())
    spec = json.loads((root / mapping["campaign.json"]).read_text())
    legacy = json.loads((root / "data/results.json").read_text())
    assert legacy["suite"] == "pilot-v0.4"
    assert data["suite"] == spec["suite"]
    assert data["protocol"]["configurations"] == spec["configurations"]
    expected = {
        (case["id"], c["id"], target, slot)
        for case in data["cases"]
        for c in spec["configurations"]
        for target in ("line", "all-to-all")
        for slot in spec["seeds"]
    }
    keys = [(r["case_id"], r["configuration_id"], r["target"], r["seed"]) for r in data["results"]]
    assert len(keys) == len(expected) and set(keys) == expected
    assert data["results"][: len(legacy["results"])] == legacy["results"]
    assert raw_path.startswith("data/campaigns/")
    return data


def test_selected_publication_is_sealed_and_legacy_is_unchanged():
    assert_publication(atlas.ROOT)


def test_old_qmap_publication_compatibility_with_expanded_registry():
    data = assert_publication(atlas.ROOT, file_map=qmap_publication_map(atlas.ROOT))
    assert all(c["compiler"] != "cirq" for c in data["protocol"]["configurations"])
    qmap = [r for r in data["results"] if r["compiler"] == "qmap"]
    owned = [c for c in data["protocol"]["configurations"] if c["compiler"] == "qmap"]
    assert len(qmap) == len(data["cases"]) * len(owned) * 2 * len(data["protocol"]["seeds"])
    assert sum(len(r["trials"]) for r in qmap) == len(qmap) * data["protocol"]["timing_repeats"]
    assert all(r["status"] == "passed" for r in qmap)


def test_cirq_publication_and_explicit_predecessor_ignore_current_selector(tmp_path, monkeypatch):
    root = campaign.create(
        tmp_path / "cohort", prepare_only=True, inherited_file_map=qmap_publication_map(atlas.ROOT)
    )
    campaign.finish(root, synthetic_document(root))
    spec = json.loads((root / "campaign.json").read_text())
    snapshot = campaign.validate_completed(root)
    mapping = {name: name for name in snapshot["files"]}
    mapping.update({name: name for name in ("snapshot-manifest.json", "MEASUREMENT_COMPLETE")})
    raw_path = f"data/campaigns/{root.name}/data/results.json"
    (root / raw_path).parent.mkdir(parents=True)
    shutil.copyfile(root / "data/results.json", root / raw_path)
    mapping["data/results.json"] = raw_path
    new_map = f"data/campaigns/{root.name}/file-map.json"
    (root / new_map).write_text(json.dumps(mapping))
    # The new selector must not affect explicitly reading/using the old source.
    (root / "publication.json").write_text(
        json.dumps({"campaign_id": root.name, "file_map": new_map})
    )
    data, _ = publication.load(root)
    assert data["suite"] == spec["suite"]
    assert data["protocol"]["configurations"] == spec["configurations"]
    assert "cirq420" in data["protocol"]["measurement_sources"]
    old_map = "predecessor-file-map.json"
    old_snapshot = json.loads((root / "history/pilot-v0.5/snapshot-manifest.json").read_text())
    inherited = {name: "history/pilot-v0.5/" + name for name in old_snapshot["files"]}
    inherited.update(
        {
            name: "history/pilot-v0.5/" + name
            for name in ("snapshot-manifest.json", "MEASUREMENT_COMPLETE")
        }
    )
    # Public artifact aliases are the unchanged literal record paths.
    old_data = json.loads((root / "history/pilot-v0.5/data/results.json").read_text())
    for row in old_data["results"]:
        for trial in row.get("trials", []):
            inherited[trial["artifact"]] = trial["artifact"]
    old_raw = "data/campaigns/predecessor/data/results.json"
    (root / old_raw).parent.mkdir(parents=True)
    shutil.copyfile(root / "history/pilot-v0.5/data/results.json", root / old_raw)
    inherited["data/results.json"] = old_raw
    (root / old_map).write_text(json.dumps(inherited))
    monkeypatch.setattr(atlas, "ROOT", root)
    with pytest.raises(ValueError, match="already owns"):
        campaign.create(tmp_path / "rejected", prepare_only=True)
    (root / "publication.json").write_text("invalid current selector")
    prepared = campaign.create(tmp_path / "explicit", prepare_only=True, inherited_file_map=old_map)
    checked = campaign.validate_workspace(prepared)
    assert checked["configurations"] == spec["configurations"]
    assert checked["measurement_configurations"] == atlas.MEASURED_CONFIGURATIONS


def test_publication_rejects_redirected_raw_data(tmp_path, monkeypatch):
    config = json.loads((atlas.ROOT / "publication.json").read_text())
    mapping = json.loads((atlas.ROOT / config["file_map"]).read_text())
    mapping["data/results.json"] = "data/results.json"
    changed = tmp_path / "file-map.json"
    changed.write_text(json.dumps(mapping))
    original = publication.relative_file
    monkeypatch.setattr(
        publication,
        "relative_file",
        lambda root, name: changed if name == config["file_map"] else original(root, name),
    )
    with pytest.raises(ValueError, match="Snapshot hash"):
        publication.load(atlas.ROOT)


def test_publication_rejects_escaping_mapping(tmp_path, monkeypatch):
    config = json.loads((atlas.ROOT / "publication.json").read_text())
    mapping = json.loads((atlas.ROOT / config["file_map"]).read_text())
    mapping["data/results.json"] = "../outside.json"
    changed = tmp_path / "file-map.json"
    changed.write_text(json.dumps(mapping))
    original = publication.relative_file
    monkeypatch.setattr(
        publication,
        "relative_file",
        lambda root, name: changed if name == config["file_map"] else original(root, name),
    )
    with pytest.raises(ValueError):
        publication.load(atlas.ROOT)
