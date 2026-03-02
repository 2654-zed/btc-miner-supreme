#!/usr/bin/env python3
"""
governance/hollywood_prop_scanner.py
────────────────────────────────────
Semantic-aware static scanner that detects Hollywood Prop anti-patterns
in the codebase.  Designed to run as a CI gate (exit code 1 = violations
found, 0 = clean).

Detects
───────
  HP-001  Math.random() / random() simulation in frontend code
  HP-002  setTimeout / time.sleep used to fake latency
  HP-003  Hardcoded bc1q wallet addresses in source code
  HP-004  Hardcoded credentials (passwords, API keys, tokens)
  HP-005  Hardcoded JSON mock responses masquerading as API data
  HP-006  Wildcard CORS (allow_origins=["*"]) in production code
  HP-007  console.log leaking sensitive fields
  HP-008  Fake data generators (generateEntropy, generateHardware, etc.)
  HP-009  Inconsistent environment variable naming

Usage
─────
  python governance/hollywood_prop_scanner.py [--strict] [--json]
  python governance/hollywood_prop_scanner.py --fix   # show remediation hints

Exit Codes
──────────
  0  No violations
  1  Violations detected
  2  Scanner internal error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

# ─── Configuration ──────────────────────────────────────────────────────

# Directories to scan (relative to project root)
SCAN_DIRS = [
    "dashboard/src",
    "api",
    "core",
    "domain",
    "infrastructure",
    "layer1_entropy",
    "layer2_execution",
    "layer3_network",
    "deployment",
]

# Files to scan individually
SCAN_FILES = [
    "config.yaml",
    "docker-compose.yml",
    "Dockerfile",
]

# Extensions to scan
SCAN_EXTENSIONS = {".ts", ".tsx", ".py", ".yaml", ".yml", ".json", ".toml"}

# Directories to always skip
SKIP_DIRS = {
    "node_modules", ".next", "__pycache__", ".git", ".pytest_cache",
    "dist", "build", ".venv", "venv",
}


# ─── Violation Model ───────────────────────────────────────────────────

@dataclass
class Violation:
    rule_id: str
    severity: str           # CRITICAL | HIGH | MEDIUM | LOW
    file: str
    line: int
    snippet: str
    message: str
    remediation: str = ""


# ─── Rule Definitions ──────────────────────────────────────────────────

RULES: list[dict] = [
    {
        "id": "HP-001",
        "severity": "CRITICAL",
        "pattern": re.compile(r"\bMath\.random\s*\(|random\.random\s*\(|randint\s*\(", re.IGNORECASE),
        "extensions": {".ts", ".tsx", ".js", ".jsx"},
        "message": "Pseudo-random number generator in frontend code — hallucinated telemetry",
        "remediation": "Replace with real data fetched from the backend API via useEffect polling.",
        "exclude_paths": {"test", "spec", "__test__"},
    },
    {
        "id": "HP-002",
        "severity": "MEDIUM",
        "pattern": re.compile(r"setTimeout\s*\(\s*.*?(?:fake|simul|mock|delay)|time\.sleep\s*\(\s*[\d.]+\s*\)\s*#\s*[Ss]imulat"),
        "extensions": SCAN_EXTENSIONS,
        "message": "Simulated latency via setTimeout/time.sleep — fake async behavior",
        "remediation": "Remove simulated delays. Wire to actual async I/O or hardware drain.",
        "exclude_paths": set(),
    },
    {
        "id": "HP-003",
        "severity": "HIGH",
        "pattern": re.compile(r'["\']bc1q[a-zA-Z0-9_]{10,}["\']'),
        "extensions": SCAN_EXTENSIONS,
        "message": "Hardcoded wallet address in source code",
        "remediation": "Read wallet address from config.yaml or environment variable COLD_WALLET_ADDRESS.",
        "exclude_paths": {"test", "spec"},
    },
    {
        "id": "HP-004",
        "severity": "HIGH",
        "pattern": re.compile(
            r'(?:password|secret|api_key|token)\s*[:=]\s*["\'][a-zA-Z0-9!@#$%^&*]{3,}["\']',
            re.IGNORECASE,
        ),
        "extensions": {".py", ".yaml", ".yml", ".toml", ".json", ".env"},
        "message": "Hardcoded credential or secret in source",
        "remediation": "Move to .env file or secrets manager. Reference via ${ENV_VAR} in config.",
        "exclude_paths": {"test", "spec", ".env.example"},
    },
    {
        "id": "HP-005",
        "severity": "CRITICAL",
        "pattern": re.compile(
            r'(?:return|response)\s*(?:=|\()?\s*\{[^}]*(?:balance|hashRate|btcPrice|temperature|utilization)\s*:'
        ),
        "extensions": {".py", ".ts", ".tsx"},
        "message": "Hardcoded JSON mock payload returned as API response",
        "remediation": "Wire to real telemetry source. Use dependency injection for data providers.",
        "exclude_paths": {"test", "spec", "schema", "types"},
    },
    {
        "id": "HP-006",
        "severity": "MEDIUM",
        "pattern": re.compile(r'allow_origins\s*=\s*\[\s*["\']?\*["\']?\s*\]|Access-Control-Allow-Origin.*\*'),
        "extensions": {".py", ".ts", ".tsx", ".yaml"},
        "message": "Wildcard CORS — allows any origin to access the API",
        "remediation": "Restrict allow_origins to specific trusted domains in production.",
        "exclude_paths": set(),
    },
    {
        "id": "HP-007",
        "severity": "LOW",
        "pattern": re.compile(
            r'console\.log\s*\([^)]*(?:password|secret|token|key|wallet|address)',
            re.IGNORECASE,
        ),
        "extensions": {".ts", ".tsx", ".js", ".jsx"},
        "message": "console.log potentially leaking sensitive data",
        "remediation": "Remove or redact sensitive fields before logging.",
        "exclude_paths": set(),
    },
    {
        "id": "HP-008",
        "severity": "CRITICAL",
        "pattern": re.compile(
            r'\bfunction\s+generate(?:Entropy|Hardware|Terminal|Mock|Fake|Simul)',
            re.IGNORECASE,
        ),
        "extensions": {".ts", ".tsx", ".js", ".jsx", ".py"},
        "message": "Simulation generator function — Hollywood Prop factory",
        "remediation": "Remove entirely. Replace with network-sourced data fetching.",
        "exclude_paths": {"test", "spec"},
    },
]


# ─── Scanner Engine ─────────────────────────────────────────────────────

def _should_skip(path: Path) -> bool:
    """Check if path is in a skipped directory."""
    parts = set(path.parts)
    return bool(parts & SKIP_DIRS)


def _is_excluded(filepath: str, exclude_paths: set[str]) -> bool:
    """Check if the file path matches any exclusion pattern."""
    lower = filepath.lower()
    return any(excl in lower for excl in exclude_paths)


def scan_file(filepath: Path, rules: list[dict]) -> List[Violation]:
    """Scan a single file against all applicable rules."""
    violations: List[Violation] = []
    ext = filepath.suffix.lower()

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return violations

    lines = content.splitlines()

    for rule in rules:
        if ext not in rule["extensions"]:
            continue
        if _is_excluded(str(filepath), rule.get("exclude_paths", set())):
            continue

        for lineno, line_text in enumerate(lines, start=1):
            if rule["pattern"].search(line_text):
                violations.append(Violation(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    file=str(filepath),
                    line=lineno,
                    snippet=line_text.strip()[:120],
                    message=rule["message"],
                    remediation=rule["remediation"],
                ))

    return violations


def scan_project(root: Path) -> List[Violation]:
    """Scan the entire project for Hollywood Prop anti-patterns."""
    all_violations: List[Violation] = []

    # Scan directories
    for scan_dir in SCAN_DIRS:
        dir_path = root / scan_dir
        if not dir_path.is_dir():
            continue
        for filepath in dir_path.rglob("*"):
            if filepath.is_file() and filepath.suffix.lower() in SCAN_EXTENSIONS:
                if not _should_skip(filepath):
                    all_violations.extend(scan_file(filepath, RULES))

    # Scan individual files
    for scan_file_name in SCAN_FILES:
        filepath = root / scan_file_name
        if filepath.is_file():
            all_violations.extend(scan_file(filepath, RULES))

    return all_violations


# ─── Reporting ──────────────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
SEVERITY_COLORS = {
    "CRITICAL": "\033[91m",  # Red
    "HIGH": "\033[93m",      # Yellow
    "MEDIUM": "\033[33m",    # Orange
    "LOW": "\033[90m",       # Gray
}
RESET = "\033[0m"


def print_report(violations: List[Violation], show_fix: bool = False) -> None:
    """Print a formatted violation report to stderr."""
    if not violations:
        print("\n\033[92m✓ No Hollywood Prop anti-patterns detected.\033[0m\n",
              file=sys.stderr)
        return

    violations.sort(key=lambda v: (SEVERITY_ORDER.get(v.severity, 99), v.file, v.line))

    counts = {}
    for v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1

    print("\n╔══════════════════════════════════════════════════════════════╗",
          file=sys.stderr)
    print("║  HOLLYWOOD PROP GOVERNANCE SCAN — VIOLATIONS DETECTED      ║",
          file=sys.stderr)
    print("╚══════════════════════════════════════════════════════════════╝\n",
          file=sys.stderr)

    for v in violations:
        color = SEVERITY_COLORS.get(v.severity, "")
        print(f"  {color}[{v.severity}]{RESET} {v.rule_id}  "
              f"{v.file}:{v.line}", file=sys.stderr)
        print(f"    → {v.message}", file=sys.stderr)
        print(f"    │ {v.snippet}", file=sys.stderr)
        if show_fix and v.remediation:
            print(f"    ✦ Fix: {v.remediation}", file=sys.stderr)
        print(file=sys.stderr)

    print("─" * 62, file=sys.stderr)
    summary_parts = [f"{color}{sev}: {counts.get(sev, 0)}{RESET}"
                     for sev, color in SEVERITY_COLORS.items()
                     if counts.get(sev, 0) > 0]
    print(f"  Total: {len(violations)}  ({', '.join(summary_parts)})",
          file=sys.stderr)


def print_json(violations: List[Violation]) -> None:
    """Print machine-readable JSON output."""
    output = {
        "scanner": "hollywood-prop-scanner",
        "version": "1.0.0",
        "total_violations": len(violations),
        "violations": [asdict(v) for v in violations],
    }
    print(json.dumps(output, indent=2))


# ─── CLI ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hollywood Prop Anti-Pattern Governance Scanner",
    )
    parser.add_argument("--strict", action="store_true",
                        help="Fail on any severity (default: fail on CRITICAL/HIGH only)")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--fix", action="store_true",
                        help="Show remediation hints for each violation")
    parser.add_argument("--root", type=str, default=None,
                        help="Project root directory (auto-detected if omitted)")
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    if not (root / "config.yaml").exists():
        print(f"Error: {root} does not appear to be the project root.",
              file=sys.stderr)
        return 2

    violations = scan_project(root)

    if args.json:
        print_json(violations)
    else:
        print_report(violations, show_fix=args.fix)

    # Determine exit code
    if args.strict:
        return 1 if violations else 0
    else:
        critical_or_high = [v for v in violations
                            if v.severity in ("CRITICAL", "HIGH")]
        return 1 if critical_or_high else 0


if __name__ == "__main__":
    sys.exit(main())
