import json

import pytest

import atlas
import publication


def test_published_campaign_is_sealed_and_legacy_is_unchanged():
    data, raw_path = publication.load(atlas.ROOT)
    legacy = json.loads((atlas.ROOT / "data/results.json").read_text())
    assert legacy["suite"] == "pilot-v0.4"
    assert data["suite"] == "pilot-v0.5-qmap-mixed-budgets"
    assert len(atlas.CONFIGURATIONS) == 13
    assert len(data["protocol"]["configurations"]) == 12
    assert len(data["results"]) == 864
    assert data["results"][:792] == legacy["results"]
    assert raw_path.startswith("data/campaigns/")
    qmap = data["results"][792:]
    assert len(qmap) == 72
    assert sum(len(r["trials"]) for r in qmap) == 216
    assert all(r["status"] == "passed" for r in qmap)


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
