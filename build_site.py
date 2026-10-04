"""Generate file://-compatible report and documentation from measured data."""

import copy
import hashlib
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import markdown

from atlas import SUITE, configuration_annotations

ROOT = Path(__file__).resolve().parent
SCORE_VERSION = "qcec-adjusted-v1"
PARTIAL_SCORE_VERSION = "qcec-adjusted-partial-v2"


def display_data(data: dict, annotations: dict | None = None) -> tuple[dict, dict]:
    """Overlay explanatory fields on a copy, leaving campaign records untouched."""
    notes = configuration_annotations() if annotations is None else annotations
    display = copy.deepcopy(data)
    standalone = data.get("kind") == "compile-retention"
    score_version = PARTIAL_SCORE_VERSION if standalone else SCORE_VERSION
    display["score_version"] = score_version
    configurations = display["protocol"].get("configurations", [])
    ids = [configuration["id"] for configuration in configurations]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate configuration ID")
    if standalone and annotations is None:
        notes = {key: value for key, value in notes.items() if key in ids}
    if notes.keys() - set(ids):
        # Historical SDK-only fixtures have no configuration annotations.
        if annotations is not None or configurations or "configurations" in display["protocol"]:
            raise ValueError("Unknown annotation configuration ID")
        notes = {}
    for identifier, note in notes.items():
        if set(note) != {"numerical_approximation", "approximation_note"}:
            raise ValueError("Only display annotation fields are allowed")
        if (
            note["numerical_approximation"] is not True
            or not isinstance(note["approximation_note"], str)
            or not note["approximation_note"].strip()
        ):
            raise ValueError("Invalid configuration annotation")
        next(c for c in configurations if c["id"] == identifier).update(note)
    sidecar = {
        "suite": data["suite"],
        "score_version": score_version,
        "protocol": {"configurations": [{"id": key, **note} for key, note in notes.items()]},
    }
    for row in display["results"]:
        for trial in row.get("trials", []):
            if trial.get("validation") is not None:
                trial["validation"].pop("details", None)
    return display, sidecar


def _publish(path, text):
    if path.exists() and path.read_text() == text:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def _validate_links(pages):
    for path, text in pages:
        for name in re.findall(r'(?:href|src)="([^"]+)"', text):
            url = urlsplit(html.unescape(name))
            if url.scheme or url.netloc or not url.path:
                continue
            destination = (path.parent / unquote(url.path)).resolve()
            if not destination.is_relative_to(ROOT.resolve()) or (
                not destination.is_file() and destination not in {p.resolve() for p, _ in pages}
            ):
                raise ValueError(f"Missing or escaping report link: {name}")


def _diagnostic_pages():
    """Render separately selected sealed evidence without changing the root selector."""
    from campaign import relative_file
    from publication import load

    pages = []
    for selector in sorted((ROOT / "diagnostics").glob("*/report.json")):
        config = json.loads(selector.read_text())
        if set(config) != {"campaign_id", "file_map"}:
            raise ValueError("Diagnostic selector must contain campaign_id and file_map")
        data, raw_path = load(ROOT, file_map=config["file_map"])
        mapping = json.loads(relative_file(ROOT, config["file_map"]).read_text())
        if data.get("kind") != "compile-retention" or data["campaign_id"] != config["campaign_id"]:
            raise ValueError("Diagnostic campaign identity mismatch")
        output = selector.parent / "index.html"

        def link(name, directory=output.parent):
            return html.escape(os.path.relpath(relative_file(ROOT, name), directory))

        rows = []
        for ordinal, row in enumerate(data["results"]):
            coverage = row["coverage"]
            metrics = row["metrics"] or {}
            details = []
            for trial in row.get("trials", []):
                check = trial["verification"]
                artifacts = " · ".join(
                    f'<a href="{link(trial[key])}">{label}</a>'
                    for key, label in [
                        ("artifact", "QASM"),
                        ("qpy_artifact", "Native QPY"),
                        ("compile_manifest", "Manifest"),
                    ]
                )
                details.append(
                    f"<div>Repeat {trial['repeat']}: {html.escape(check['state'])}; "
                    f"{html.escape(check['reason'] or check['criterion'] or 'none')}; "
                    f"{check['wall_seconds']:.3f} s / "
                    f"{check['effective_budget_seconds']:.3f} s cap · {artifacts}</div>"
                )

            def value(key, values=metrics):
                return str(values.get(key, "N/A"))

            compile_time = "N/A" if row["compile_ms"] is None else f"{row['compile_ms'] / 1000:.3f}"
            rows.append(
                f'<tr data-identity="{ordinal}"><td>{ordinal:02d} / '
                f"<code>{html.escape(row['case_id'])}</code></td>"
                f"<td>{html.escape(row['target'])}</td>"
                f"<td>{html.escape(row['configuration_id'])} / {row['seed']}</td>"
                f'<td class="status">{html.escape(row["status"])}</td>'
                f"<td>{coverage['compiled']}/{coverage['required_repeats']} saved; "
                f"{coverage['accepted_repeats']}/{coverage['required_repeats']} accepted</td>"
                f"<td>{value('two_qubit_count')} / {value('two_qubit_depth')}</td>"
                f"<td>{value('one_qubit_count')} / {value('total_depth')}</td>"
                f"<td>{compile_time}</td>"
                f"<td><details><summary>Checks / artifacts</summary>"
                f"{''.join(details)}</details></td></tr>"
            )
        compiled = sum(r["coverage"]["compiled"] for r in data["results"])
        accepted = sum(r["coverage"]["accepted_repeats"] for r in data["results"])
        required = len(data["results"]) * data["protocol"]["timing_repeats"]
        environment = data["environment"]
        evidence = (
            f'<a href="{link(raw_path)}">Sealed raw JSON</a> · '
            f'<a href="{link(config["file_map"])}">Exact FileMap</a> · '
            f'<a href="{link(mapping["snapshot-manifest.json"])}">Snapshot</a> · '
            f'<a href="{link(mapping["MEASUREMENT_COMPLETE"])}">Completion marker</a>'
            f"<p><code>{html.escape(data['campaign_id'])}</code></p>"
        )
        tokens = {
            "__ROOT__": os.path.relpath(ROOT, output.parent) + "/",
            "__SUMMARY__": (
                f"{len(rows)} identities · {compiled}/{required} committed repeats · "
                f"{accepted}/{required} strict accepts"
            ),
            "__ENVIRONMENT__": html.escape(
                f"{environment['cpu']}; affinity {environment['cpu_affinity']}; "
                f"Python {environment['python']}. No exclusive host or enforced memory cap."
            ),
            "__ROWS__": "".join(rows),
            "__EVIDENCE__": evidence,
        }
        report = (ROOT / "web/diagnostic.html").read_text()
        for token, value in tokens.items():
            report = report.replace(token, value)
        report = report.replace(
            "<!doctype html>",
            "<!doctype html>\n<!-- Generated by build_site.py; do not edit. -->",
            1,
        )
        pages.append((output, report))
    return pages


def build() -> None:
    raw_path = "data/results.json"
    is_publication = (ROOT / "publication.json").exists()
    if is_publication:
        from publication import load

        data, raw_path = load(ROOT)
    else:
        data = json.loads((ROOT / raw_path).read_text())
    sidecar_path = (ROOT / raw_path).parent / "configuration-notes.json"
    is_campaign = (ROOT / "campaign.json").exists()
    if is_campaign:
        from campaign import validate_completed

        validate_completed(ROOT)
    elif data["suite"] == SUITE and not is_publication:
        raise ValueError("New suite requires a sealed campaign")
    display, sidecar = display_data(data)
    if is_campaign or is_publication:
        sidecar.update(
            campaign_id=data["campaign_id"],
            raw_sha256=hashlib.sha256((ROOT / raw_path).read_bytes()).hexdigest(),
        )
    payload = json.dumps(display, ensure_ascii=False).replace("<", "\\u003c")
    template = (ROOT / "web/report.html").read_text()
    if template.count("__BENCHMARK_DATA__") != 1:
        raise ValueError("Expected exactly one data placeholder")
    report = template.replace("__BENCHMARK_DATA__", payload)
    if is_publication:
        report = report.replace('href="data/results.json"', f'href="{html.escape(raw_path)}"')
        report = report.replace(
            'href="data/configuration-notes.json"',
            f'href="{html.escape(str(sidecar_path.relative_to(ROOT)))}"',
        )
        report = report.replace(
            '<a href="data/manifest.json">Input manifest</a>',
            '<a href="data/manifest.json">Input manifest</a>'
            '<a href="data/results.json">v0.4 Raw JSON (reused source)</a>',
        )
    report = report.replace(
        "<!doctype html>", "<!doctype html>\n<!-- Generated by build_site.py; do not edit. -->", 1
    )
    pages = [(ROOT / "index.html", report)]
    diagnostic_pages = _diagnostic_pages()
    diagnostic_nav = "".join(
        f'<a href="../{html.escape(path.relative_to(ROOT).as_posix())}">'
        "Compile retention diagnostic</a>"
        for path, _ in diagnostic_pages
    )
    style = """
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
    font:14px/1.8 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
    main{max-width:1040px;margin:auto;padding:35px 30px 70px}a{color:var(--accent);
    text-underline-offset:4px}nav{border-bottom:1px solid var(--border);padding-bottom:20px;
    margin-bottom:35px;display:flex;gap:25px;flex-wrap:wrap;font-size:13px}
    h1{font-size:32px;line-height:1.5;letter-spacing:-.7px}h2{font-size:23px;
    border-top:1px solid var(--border);padding-top:25px;margin-top:45px}h3{font-size:18px}
    .table-scroll{overflow:auto;margin:20px 0}table{border-collapse:collapse;
    font-size:13px;min-width:700px;width:100%;background:var(--bg)}
    th,td{padding:12px;border:1px solid var(--border);text-align:left;vertical-align:top}
    th{background:var(--surface)}code{font:12px/1.8 ui-monospace,monospace;
    background:var(--code-bg);
    padding:2px 5px;overflow-wrap:anywhere}pre{padding:18px;overflow:auto;
    background:var(--pre-bg);color:var(--pre-text);border-radius:6px}
    pre code{background:none;padding:0}
    blockquote{border-left:3px solid #8d77e5;padding-left:20px;color:var(--muted)}
    @media(max-width:600px){main{padding:20px}h1{font-size:26px}}
    """
    for source in sorted((ROOT / "docs").glob("*.md")):
        text = source.read_text()
        text = re.sub(r"\]\(([^)\s]+)\.md(#[^)]*)?\)", r"](\1.html\2)", text)
        body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
        body = body.replace("<table>", '<div class="table-scroll"><table>')
        body = body.replace("</table>", "</table></div>")
        title = html.escape(source.read_text().splitlines()[0].removeprefix("# "))
        page = (
            "<!doctype html>\n<!-- Generated by build_site.py; do not edit. -->\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title} | Transpiler Atlas</title>"
            '<script src="../web/theme.js"></script>'
            '<link rel="stylesheet" href="../web/theme.css">'
            f"<style>{style}</style></head>"
            '<body><main><nav aria-label="Documentation navigation">'
            '<a href="../index.html">← Results</a>'
            '<a href="pilot.html">Protocol</a><a href="methodology.html">Scoring</a>'
            '<a href="research.html">Sources</a>'
            f"{diagnostic_nav}"
            '<label class="theme-control" for="theme">Theme<select id="theme">'
            '<option value="light">Light</option><option value="dark">Dark</option>'
            '<option value="system" selected>System</option></select></label>'
            f"</nav>{body}</main></body></html>\n"
        )
        pages.append((source.with_suffix(".html"), page))
    pages.extend(diagnostic_pages)
    if is_campaign or is_publication:
        # Sidecar is a builder-owned link target, not a measurement artifact.
        _validate_links([*pages, (sidecar_path, "")])
    _publish(
        sidecar_path,
        json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n",
    )
    for path, page in pages[1:]:
        _publish(path, page)
    _publish(*pages[0])
    print("Built index.html and docs/*.html from measured data")


if __name__ == "__main__":
    build()
