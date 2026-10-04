"""The standalone browser-fixture command must work from a fresh scratch cwd."""

import os
import subprocess
import sys
from pathlib import Path

import atlas


def test_campaign_site_fixture_initializes_its_scratch_parent(tmp_path):
    assert not (tmp_path / ".checks/tmp").exists()
    command = subprocess.run(
        [sys.executable, str(atlas.ROOT / "tests/make_campaign_site.py")],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(atlas.ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert command.returncode == 0, command.stderr
    root = Path(command.stdout.strip().splitlines()[-1])
    assert root.is_relative_to(tmp_path / ".checks/tmp")
    assert (root / "index.html").is_file()
    assert (root / "MEASUREMENT_COMPLETE").is_file()
