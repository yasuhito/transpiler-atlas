"""Select an immutable predecessor by its sealed ownership, never by current selector."""

from pathlib import Path

import publication


def qmap_publication_map(root):
    matches = []
    for path in sorted((Path(root) / "data/campaigns").glob("*/file-map.json")):
        name = str(path.relative_to(root))
        data, _ = publication.load(root, file_map=name)
        ids = {c["id"] for c in data["protocol"]["configurations"]}
        if "qmap-sc-heuristic-maponly-v1" in ids and "cirq-routecqc-maponly-v1" not in ids:
            matches.append(name)
    if len(matches) != 1:
        raise ValueError("Expected one sealed QMAP-only predecessor, select explicitly")
    return matches[0]
