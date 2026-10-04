"""Synthetic, unmeasured browser fixture; never run a campaign worker."""

import tempfile
from pathlib import Path

from publication_fixtures import qmap_publication_map
from test_campaign import synthetic_document

import build_site
import campaign

if __name__ == "__main__":
    scratch = Path(".checks/tmp")
    scratch.mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix="site-fixture-", dir=scratch))
    workspace = campaign.create(
        parent, prepare_only=True, inherited_file_map=qmap_publication_map(build_site.ROOT)
    )
    campaign.finish(workspace, synthetic_document(workspace))
    build_site.ROOT = workspace
    build_site.build()
    print(workspace)
