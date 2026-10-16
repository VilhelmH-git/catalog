#!/usr/bin/env python3
"""Points catalog entries of products we do not release ourselves at their latest release.

A product with "upstream": "<owner>/<repo>" in catalog.json is released by someone
else, so no release script of ours updates its entry. This fills it the way
set_entry.py (claude-kit tools/catalog) does: `version`, `releaseNotes`, and `url`,
`sha256`, `size` for every object with a `pattern`. It only edits the local
catalog.json and prints what changed; .github/workflows/upstream.yml turns that
into a pull request, because merging it ships outside code to every colleague.

    GH_TOKEN=... python tools/upstream.py [catalog.json]

Exit codes: 0 done (changed or not), 1 an entry could not be filled.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


def api(path: str) -> dict:
    request = urllib.request.Request(f"https://api.github.com/{path}", headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "catalog-upstream",
        **({"Authorization": f"Bearer {os.environ['GH_TOKEN']}"} if os.environ.get("GH_TOKEN") else {}),
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text.lstrip("vV").split("+")[0])[:4]) or (0,)


def resolve(node, assets: list[dict], where: str) -> None:
    """Fills url/sha256/size of every object with a pattern; exactly one asset must match."""
    if isinstance(node, dict):
        if "pattern" in node:
            hits = [a for a in assets if fnmatch.fnmatch(a["name"], node["pattern"])]
            if len(hits) != 1:
                raise ValueError(f"{where}: pattern {node['pattern']!r} matches {len(hits)} assets")
            digest = hits[0].get("digest") or ""
            if not digest.startswith("sha256:"):
                raise ValueError(f"{where}: {hits[0]['name']} has no sha256 digest")
            node.update(url=hits[0]["browser_download_url"], sha256=digest[7:], size=hits[0]["size"])
        for key, value in node.items():
            resolve(value, assets, f"{where}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            resolve(value, assets, f"{where}[{i}]")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "catalog.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    changed, failed = [], False
    for product in doc["products"]:
        repo = product.get("upstream")
        if not repo:
            continue
        release = api(f"repos/{repo}/releases/latest")
        tag = release["tag_name"]
        if version_tuple(tag) <= version_tuple(product.get("version") or "0"):
            print(f"{product['id']}: {product.get('version')} is current ({repo} {tag})")
            continue
        try:
            resolve({k: v for k, v in product.items() if k not in ("id", "upstream")}, release["assets"], product["id"])
        except ValueError as error:
            print(f"::error::{error}")
            failed = True
            continue
        old = product.get("version")
        product["version"] = tag.lstrip("vV")
        product["releaseNotes"] = release["html_url"]
        changed.append(f"{product['id']} {old} -> {product['version']} ({release['html_url']})")
    if changed:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for line in changed:
            print(line)
        if out := os.environ.get("GITHUB_OUTPUT"):
            with open(out, "a", encoding="utf-8") as f:
                f.write("changed<<EOF\n" + "\n".join(changed) + "\nEOF\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
