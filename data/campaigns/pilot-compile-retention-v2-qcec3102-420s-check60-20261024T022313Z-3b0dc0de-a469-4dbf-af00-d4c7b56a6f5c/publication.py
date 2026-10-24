"""Resolve a sealed campaign against byte-identical repository files without duplication."""

import json
from pathlib import Path

from campaign import relative_file, validate_completed


def load(root, *, file_map=None):
    """Read the current selector, or an explicitly selected immutable FileMap."""
    root = Path(root)
    config = (
        json.loads(relative_file(root, "publication.json").read_text())
        if file_map is None
        else None
    )
    mapping = json.loads(
        relative_file(root, config["file_map"] if config else file_map).read_text()
    )

    def resolve(name):
        return relative_file(root, mapping[name])

    snapshot = validate_completed(root, resolve)
    if config is not None and snapshot["campaign_id"] != config["campaign_id"]:
        raise ValueError("Publication campaign identity mismatch")
    expected = set(snapshot["files"]) | {"MEASUREMENT_COMPLETE", "snapshot-manifest.json"}
    if set(mapping) != expected:
        raise ValueError("Publication file map does not cover exactly the sealed files")
    raw_path = mapping["data/results.json"]
    if not raw_path.startswith("data/campaigns/"):
        raise ValueError("Publication raw data must use a new campaign path")
    data = json.loads(resolve("data/results.json").read_text())
    for row in data["results"]:
        for trial in row.get("trials", []):
            for key in ("artifact", "qpy_artifact", "compile_manifest"):
                if key in trial and resolve(trial[key]) != relative_file(root, trial[key]):
                    raise ValueError("Published artifact link does not resolve to the sealed bytes")
    return data, raw_path
