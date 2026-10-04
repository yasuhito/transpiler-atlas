"""Small real control workspace for browser regressions, not campaign measurements."""

import subprocess
import sys
import tempfile
from pathlib import Path

import retention as h
import retention_campaign as campaign

base = Path("/tmp/ta-hardto/test-sites")
base.mkdir(parents=True, exist_ok=True)
into = Path(tempfile.mkdtemp(prefix="retention-controls-", dir=base))
root = campaign.create(
    into,
    prepare_only=True,
    identities=[h.Job("qft-4q", config, "line", 7) for config in ("qiskit-l1", "qiskit-l2")],
)
control = subprocess.run(
    [sys.executable, str(root / "atlas.py"), "retention-run"],
    cwd=root,
    capture_output=True,
    text=True,
    timeout=60,
)
if control.returncode:
    raise RuntimeError(control.stderr)
print(campaign.preview(root, into / "preview"))
