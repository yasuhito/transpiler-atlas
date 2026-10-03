"""Synthetic, unmeasured browser fixture; never run a campaign worker."""

import tempfile
from pathlib import Path

from test_campaign import synthetic_document

import build_site
import campaign

if __name__ == "__main__":
    parent = Path(tempfile.mkdtemp(prefix="site-fixture-", dir=".checks/tmp"))
    workspace = campaign.create(parent, prepare_only=True)
    campaign.finish(workspace, synthetic_document(workspace))
    build_site.ROOT = workspace
    build_site.build()
    print(workspace)
