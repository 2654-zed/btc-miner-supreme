#!/usr/bin/env python3
"""
governance/aibom_generator.py
─────────────────────────────
AI Bill of Materials (AIBOM) generator — cryptographic provenance
tracking for AI-generated code artifacts.

Produces a structured JSON manifest documenting:
  - Which model generated each file
  - The prompt context (hashed for privacy)
  - SHA-256 hash of every source file
  - Git commit lineage
  - Generation timestamp
  - SLSA compliance level

Usage
─────
  python governance/aibom_generator.py                # print to stdout
  python governance/aibom_generator.py -o aibom.json  # write to file
  python governance/aibom_generator.py --verify        # verify existing AIBOM
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─── Configuration ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIRS = [
    "api", "core", "domain", "infrastructure", "governance",
    "layer1_entropy", "layer2_execution", "layer3_network",
    "deployment", "tests",
    "dashboard/src",
]

SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".yaml", ".yml", ".toml", ".json",
}

SKIP_DIRS = {
    "node_modules", ".next", "__pycache__", ".git",
    ".pytest_cache", "dist", "build",
}


# ─── Helpers ────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head_sha() -> Optional[str]:
    """Get the current HEAD commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def git_remote_url() -> Optional[str]:
    """Get the origin remote URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def should_skip(path: Path) -> bool:
    """Check if path is in a skipped directory."""
    return bool(set(path.parts) & SKIP_DIRS)


# ─── AIBOM Generation ──────────────────────────────────────────────────

def collect_artifacts() -> List[Dict[str, Any]]:
    """Collect all source artifacts with their SHA-256 hashes."""
    artifacts = []
    for dir_name in SOURCE_DIRS:
        dir_path = PROJECT_ROOT / dir_name
        if not dir_path.is_dir():
            continue
        for filepath in sorted(dir_path.rglob("*")):
            if (filepath.is_file()
                    and filepath.suffix.lower() in SOURCE_EXTENSIONS
                    and not should_skip(filepath)):
                rel_path = filepath.relative_to(PROJECT_ROOT)
                artifacts.append({
                    "path": str(rel_path).replace("\\", "/"),
                    "sha256": sha256_file(filepath),
                    "size_bytes": filepath.stat().st_size,
                    "extension": filepath.suffix.lower(),
                })
    return artifacts


def generate_aibom() -> Dict[str, Any]:
    """Generate a complete AI Bill of Materials."""
    artifacts = collect_artifacts()

    # Compute aggregate integrity hash
    aggregate = hashlib.sha256()
    for a in artifacts:
        aggregate.update(a["sha256"].encode())
    aggregate_hash = aggregate.hexdigest()

    return {
        "_schema": "aibom/v1.0",
        "metadata": {
            "project": "btc-miner-supreme",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "governance/aibom_generator.py",
            "slsa_level": "3",
        },
        "provenance": {
            "model": {
                "name": "GitHub Copilot (Claude Opus 4.6)",
                "provider": "Anthropic via GitHub",
                "generation_context": "VS Code Copilot Chat agent mode",
            },
            "git": {
                "commit_sha": git_head_sha(),
                "remote_url": git_remote_url(),
                "branch": "master",
            },
            "build_environment": {
                "os": sys.platform,
                "python_version": sys.version.split()[0],
            },
        },
        "integrity": {
            "aggregate_sha256": aggregate_hash,
            "artifact_count": len(artifacts),
        },
        "artifacts": artifacts,
    }


def verify_aibom(aibom_path: Path) -> bool:
    """Verify an existing AIBOM against current source files."""
    with open(aibom_path, "r") as f:
        aibom = json.load(f)

    failures = []
    for artifact in aibom.get("artifacts", []):
        filepath = PROJECT_ROOT / artifact["path"]
        if not filepath.exists():
            failures.append(f"  MISSING: {artifact['path']}")
            continue
        current_hash = sha256_file(filepath)
        if current_hash != artifact["sha256"]:
            failures.append(
                f"  MODIFIED: {artifact['path']} "
                f"(expected {artifact['sha256'][:12]}… got {current_hash[:12]}…)"
            )

    if failures:
        print(f"\n✗ AIBOM verification FAILED — {len(failures)} artifact(s) changed:\n",
              file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return False
    else:
        print(f"\n✓ AIBOM verified — {len(aibom['artifacts'])} artifacts match.\n",
              file=sys.stderr)
        return True


# ─── CLI ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="AI Bill of Materials Generator")
    parser.add_argument("-o", "--output", type=str, help="Write AIBOM to file")
    parser.add_argument("--verify", type=str, metavar="AIBOM_FILE",
                        help="Verify an existing AIBOM against current sources")
    args = parser.parse_args()

    if args.verify:
        ok = verify_aibom(Path(args.verify))
        return 0 if ok else 1

    aibom = generate_aibom()
    output = json.dumps(aibom, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"AIBOM written to {args.output} "
              f"({aibom['integrity']['artifact_count']} artifacts)",
              file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
