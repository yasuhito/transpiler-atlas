import copy
import json

import pytest
from test_campaign import synthetic_document

import atlas
import campaign
import mixed_sources


@pytest.fixture
def sealed(tmp_path):
    root = campaign.create(tmp_path / "campaigns", prepare_only=True)
    campaign.finish(root, synthetic_document(root))
    return root, json.loads((root / "data/results.json").read_text())


def test_budget_provenance_not_a_uniform_retry_budget(sealed):
    root, data = sealed
    old = data["results"][:792]
    budgets = [mixed_sources.record_budget_seconds(data, row) for row in old]
    assert budgets.count(120) == 750
    assert budgets.count(600) == 42
    assert all(mixed_sources.record_budget_seconds(data, r) == 420 for r in data["results"][792:])
    p = data["protocol"]["measurement_sources"]["v0.4"]["protocol"]
    assert p["initial_worker_timeout_seconds"] == 120
    assert p["worker_timeout_seconds"] == 600
    assert p["timeout_retry_entries"] == 42
    assert p["initial_attempt_snapshot"] == "data/attempts/pilot-v0.4-120s.json"
    assert (root / "history/pilot-v0.4" / p["initial_attempt_snapshot"]).is_file()
    assert data["protocol"]["reference_configuration"] == "qiskit-l2"
    assert len(data["results"]) == 936
    assert set(data["protocol"]["measurement_sources"]) == {"v0.4", "qmap420", "cirq420"}


def test_reused_records_are_exact_and_artifacts_resolve(sealed):
    root, data = sealed
    legacy = mixed_sources.load_legacy(root)
    assert mixed_sources.canonical_record_digest(
        data["results"][:792]
    ) == mixed_sources.canonical_record_digest(legacy["results"])
    for row in legacy["results"]:
        for trial in row.get("trials", []):
            assert campaign.digest(root / trial["artifact"]) == campaign.digest(
                atlas.ROOT / trial["artifact"]
            )
    changed = copy.deepcopy(data)
    changed["results"][0]["status"] = "invented"
    with pytest.raises(ValueError, match="provenance"):
        mixed_sources.validate_combined(root, changed)


def test_worker_rejects_unmeasured_legacy_configuration(sealed):
    root, data = sealed
    # Completed roots reject every job; use a fresh prepared root to test membership.
    fresh = campaign.create(root.parent / "next", prepare_only=True)
    (fresh / "RUN_STARTED").write_text("test\n")
    case = campaign.input_cases(fresh)[0]
    with pytest.raises(ValueError, match="schedule"):
        campaign.validate_worker(fresh, case, "bqskit-l3", "line", 19)
    with pytest.raises(ValueError, match="schedule"):
        campaign.validate_worker(fresh, case, "qmap-sc-heuristic-maponly-v1", "line", 19)
    campaign.validate_worker(fresh, case, "cirq-routecqc-maponly-v1", "line", 19)
