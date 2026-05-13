import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger(__name__)

EXTERNAL_INTEL_ROOT = BASE_PATH / "tmp_agent" / "external_intel"
KNOWLEDGE_EXTERNAL_ROOT = BASE_PATH / "tmp_agent" / "knowledge" / "external"
LOGS_ROOT = BASE_PATH / "tmp_agent" / "logs"
LEARNING_EVENTS_PATH = LOGS_ROOT / "learning_events.ndjson"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(owner: str, repo: str) -> str:
    return f"{owner}_{repo}".replace("-", "_")


def _append_event(event: str, payload: Dict[str, Any]) -> None:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    row = {"ts_utc": _utc_now(), "event": event, **payload}
    with open(LEARNING_EVENTS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def _http_get_json(url: str) -> Dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    headers = {
        "User-Agent": "AI_VAULT-Brain-Learning/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str) -> str:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    headers = {"User-Agent": "AI_VAULT-Brain-Learning/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_contents_url(item: Dict[str, Any]) -> Optional[str]:
    if item.get("type") != "file":
        return None
    name = str(item.get("name") or "").lower()
    if name in {
        "readme.md",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "setup.py",
        "setup.cfg",
        "tox.ini",
        "pytest.ini",
        "pipfile",
    }:
        return item.get("download_url")
    return None


def _fetch_root_index(api_url: str) -> List[Dict[str, Any]]:
    try:
        payload = _http_get_json(f"{api_url}/contents")
        if isinstance(payload, list):
            return payload
    except Exception:
        return []
    return []


def _fetch_repo_tree(api_url: str, default_branch: str) -> List[Dict[str, Any]]:
    try:
        payload = _http_get_json(f"{api_url}/git/trees/{default_branch}?recursive=1")
        if isinstance(payload, dict):
            return list(payload.get("tree", []) or [])
    except Exception:
        return []
    return []


def _priority_file_score(path_value: str) -> int:
    path_l = path_value.lower()
    score = 0
    if any(token in path_l for token in ("agent", "tool", "graph", "router", "checkpoint", "govern", "memory", "critic", "judge", "eval", "prompt", "orchestr")):
        score += 4
    if any(path_l.endswith(ext) for ext in (".py", ".ts", ".tsx", ".js", ".md", ".toml", ".json", ".yaml", ".yml")):
        score += 2
    if any(path_l.startswith(prefix) for prefix in ("tests/", "docs/", ".github/", "src/", "examples/", "packages/")):
        score += 2
    if "readme" in path_l:
        score += 1
    return score


def _fetch_priority_file_text(api_url: str, file_path: str) -> str:
    meta = _http_get_json(f"{api_url}/contents/{quote(file_path, safe='/')}")
    download_url = meta.get("download_url")
    if download_url:
        return _http_get_text(download_url)
    if meta.get("content") and meta.get("encoding") == "base64":
        import base64
        return base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    return ""


def _build_priority_file_artifacts(api_url: str, default_branch: str, local_dir: Path) -> Dict[str, str]:
    tree = _fetch_repo_tree(api_url, default_branch)
    tree_path = local_dir / "repo_tree_index.json"
    write_json(tree_path, tree)
    candidates = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path_value = str(item.get("path") or "")
        score = _priority_file_score(path_value)
        if score <= 0:
            continue
        candidates.append({"path": path_value, "score": score, "size": int(item.get("size") or 0)})
    candidates.sort(key=lambda row: (row["score"], -row["size"], row["path"]), reverse=True)
    candidates = candidates[:14]
    catalog_path = local_dir / "priority_file_catalog.json"
    write_json(catalog_path, candidates)
    snippets = []
    for item in candidates:
        path_value = item["path"]
        try:
            content = _fetch_priority_file_text(api_url, path_value)
        except Exception:
            content = ""
        excerpt = content[:4000]
        snippets.append({
            "path": path_value,
            "score": item["score"],
            "size": item["size"],
            "excerpt": excerpt,
        })
    snippets_path = local_dir / "priority_file_snippets.json"
    write_json(snippets_path, snippets)
    return {
        "repo_tree_index_path": str(tree_path),
        "priority_file_catalog_path": str(catalog_path),
        "priority_file_snippets_path": str(snippets_path),
    }


def ingest_github_repo(owner: str, repo: str, *, force_refresh: bool = False) -> Dict[str, Any]:
    source_slug = _slug(owner, repo)
    source_id = f"github_{source_slug}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    repo_url = f"https://github.com/{owner}/{repo}"
    local_dir = EXTERNAL_INTEL_ROOT / "github" / source_slug
    local_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = local_dir / "source_manifest.json"
    metadata_path = local_dir / "repo_metadata.json"
    readme_path = local_dir / "README.snapshot.md"
    root_index_path = local_dir / "root_index.json"
    dependency_hints_path = local_dir / "dependency_hints.json"

    if manifest_path.exists() and not force_refresh:
        manifest = read_json(manifest_path, default={}) or {}
        manifest.setdefault("source_id", source_id)
        manifest.setdefault("local_path", str(local_dir))
        return manifest

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    metadata = _http_get_json(api_url)
    root_index = _fetch_root_index(api_url)
    default_branch = str(metadata.get("default_branch") or "main")

    readme_text = ""
    readme_download_url: Optional[str] = None
    try:
        readme_meta = _http_get_json(f"{api_url}/readme")
        readme_download_url = readme_meta.get("download_url")
        if readme_download_url:
            readme_text = _http_get_text(readme_download_url)
    except urllib.error.HTTPError:
        readme_text = ""
    except Exception as exc:
        log.warning("readme fetch failed for %s/%s: %s", owner, repo, exc)

    if readme_text:
        readme_path.write_text(readme_text, encoding="utf-8")
    write_json(metadata_path, metadata)
    write_json(root_index_path, root_index)
    deep_artifacts = _build_priority_file_artifacts(api_url, default_branch, local_dir)

    dependency_hints: Dict[str, str] = {}
    for item in root_index:
        dl = _safe_contents_url(item)
        if not dl:
            continue
        try:
            dependency_hints[item.get("name")] = _http_get_text(dl)[:12000]
        except Exception:
            continue
    write_json(dependency_hints_path, dependency_hints)

    manifest = {
        "source_id": source_id,
        "source_type": "github_repo",
        "url": repo_url,
        "owner": owner,
        "repo": repo,
        "ingested_at_utc": _utc_now(),
        "local_path": str(local_dir),
        "status": "downloaded",
        "hash": _sha256_text(json.dumps(metadata, sort_keys=True)),
        "files_indexed": len(root_index) + (1 if readme_text else 0),
        "repo_api_url": api_url,
        "readme_download_url": readme_download_url,
        "root_index_path": str(root_index_path),
        "dependency_hints_path": str(dependency_hints_path),
        **deep_artifacts,
    }
    write_json(manifest_path, manifest)
    _append_event("source_ingested", {"source_id": source_id, "url": repo_url, "local_path": str(local_dir)})
    return manifest
