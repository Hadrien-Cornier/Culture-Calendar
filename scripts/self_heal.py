#!/usr/bin/env python3
"""Self-healing agent for the Culture Calendar pipeline.

Triggered when a pipeline-failure issue is opened (or manually via
workflow_dispatch). Diagnoses the failure from workflow logs, generates
a code fix using Claude, applies it, runs tests, and creates a PR.

Also runs as a scheduled health check for content freshness (stale data,
venues with zero upcoming events).

Usage:
    python scripts/self_heal.py --issue 44          # heal from issue
    python scripts/self_heal.py --run 29671592970   # heal from workflow run
    python scripts/self_heal.py --health-check      # content freshness check
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import anthropic
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

GITHUB_API = "https://api.github.com"
REPO = "Hadrien-Cornier/Culture-Calendar"
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_FIX_ATTEMPTS = 2


def _gh_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GH_TOKEN/GITHUB_TOKEN not set")
        sys.exit(1)
    return token


def _gh_headers() -> dict:
    return {
        "Authorization": f"token {_gh_token()}",
        "Accept": "application/vnd.github.v3+json",
    }


def _claude_client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ANTHROPIC_API_KEY not set")
        sys.exit(1)
    return anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=2)


# ---------------------------------------------------------------------------
# Fetch failure context
# ---------------------------------------------------------------------------


def fetch_run_logs(run_id: str) -> str:
    """Download the failed step's log excerpt from a workflow run."""
    resp = requests.get(
        f"{GITHUB_API}/repos/{REPO}/actions/runs/{run_id}/logs",
        headers=_gh_headers(),
        timeout=30,
    )
    if resp.status_code == 302:
        # Follow redirect to the actual log archive
        resp = requests.get(resp.headers["Location"], timeout=60)
    if not resp.ok:
        return f"(Could not fetch logs: HTTP {resp.status_code})"

    # The logs endpoint returns a zip; extract text from it
    import io
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        excerpts = []
        for name in sorted(zf.namelist()):
            if "Run " in name or "error" in name.lower() or "fail" in name.lower():
                text = zf.read(name).decode("utf-8", errors="replace")
                # Keep only error-relevant lines
                lines = [
                    l
                    for l in text.splitlines()
                    if any(
                        kw in l.lower()
                        for kw in [
                            "error",
                            "fail",
                            "exception",
                            "traceback",
                            "❌",
                            "⚠️",
                            "warning",
                        ]
                    )
                ]
                if lines:
                    excerpts.append(f"--- {name} ---\n" + "\n".join(lines[-30:]))
        return "\n\n".join(excerpts) if excerpts else "(No error lines found in logs)"
    except zipfile.BadZipFile:
        return resp.text[:5000]


def fetch_issue(issue_number: int) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}",
        headers=_gh_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def extract_run_id_from_issue(issue_body: str) -> Optional[str]:
    m = re.search(r"/actions/runs/(\d+)", issue_body or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Identify the failing component
# ---------------------------------------------------------------------------


def identify_failing_scraper(logs: str) -> Optional[str]:
    """Extract which scraper/venue failed from the logs."""
    patterns = [
        r"❌\s+\[\d+/\d+\]\s+(\w+)",
        r"Error scraping\s+(.+?)(?:\s*:|\s*$)",
        r"(\w+Scraper)\s+failed",
        r"Failed\s+-\s+(.+?)(?:\s*$|\s*:)",
    ]
    for pat in patterns:
        m = re.search(pat, logs, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def find_scraper_file(scraper_name: str) -> Optional[Path]:
    """Map a scraper display name to its source file."""
    # Normalize: "ArtAustin" -> "art_austin", "AFS" -> "afs"
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", scraper_name).lower()
    candidates = [
        REPO_ROOT / "src" / "scrapers" / f"{snake}_scraper.py",
        REPO_ROOT / "src" / "scrapers" / f"{scraper_name.lower()}_scraper.py",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Glob fallback
    for p in (REPO_ROOT / "src" / "scrapers").glob("*_scraper.py"):
        if snake in p.stem.lower():
            return p
    return None


# ---------------------------------------------------------------------------
# Claude diagnosis + fix generation
# ---------------------------------------------------------------------------


def diagnose_and_fix(
    client: anthropic.Anthropic,
    logs: str,
    scraper_name: Optional[str],
    scraper_code: Optional[str],
    scraper_file: Optional[str],
    attempt: int = 1,
    previous_error: str = "",
) -> dict:
    """Ask Claude to diagnose the failure and generate a fix.

    Returns:
        {
            "diagnosis": "...",
            "fix": {
                "file": "src/scrapers/foo_scraper.py",
                "old_text": "...",
                "new_text": "...",
            } | None,
            "confidence": "high" | "medium" | "low",
        }
    """
    context_parts = [
        "## Pipeline Failure Logs",
        f"```\n{logs[:8000]}\n```",
    ]

    if scraper_name and scraper_code:
        context_parts.extend(
            [
                f"\n## Scraper: {scraper_name}",
                f"File: `{scraper_file}`",
                f"```python\n{scraper_code[:12000]}\n```",
            ]
        )

    if previous_error:
        context_parts.extend(
            [
                f"\n## Previous Fix Attempt Failed",
                f"Tests failed with:\n```\n{previous_error[:3000]}\n```",
                "Please generate a DIFFERENT fix.",
            ]
        )

    context = "\n".join(context_parts)

    prompt = f"""You are a debugging agent for the Culture Calendar pipeline, which scrapes
Austin cultural event venues and publishes them to a website.

A pipeline run has failed. Your job:
1. Diagnose the root cause from the logs
2. Generate a minimal code fix

{context}

## Instructions

Analyze the failure and respond with ONLY valid JSON (no markdown fences):

{{
  "diagnosis": "One paragraph explaining the root cause",
  "confidence": "high|medium|low",
  "fix": {{
    "file": "relative/path/to/file.py",
    "old_text": "exact text to replace (must match the file exactly)",
    "new_text": "replacement text"
  }}
}}

Rules:
- If you can identify a specific code fix, include the "fix" object
- "old_text" must be an EXACT substring of the current file content
- If the failure is a transient issue (site down, rate limit) with no code fix needed, set "fix" to null
- If the failure is in a file you don't have, set "fix" to null and explain in the diagnosis
- Keep the fix minimal - change only what's needed
- Common fixes: update CSS selectors, fix date parsing, add error handling, update URL patterns
"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    # Parse JSON from response
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start == -1 or json_end <= json_start:
        return {
            "diagnosis": f"Could not parse Claude response: {text[:500]}",
            "fix": None,
            "confidence": "low",
        }

    try:
        return json.loads(text[json_start:json_end])
    except json.JSONDecodeError:
        return {
            "diagnosis": f"Invalid JSON in Claude response: {text[:500]}",
            "fix": None,
            "confidence": "low",
        }


# ---------------------------------------------------------------------------
# Apply fix + test
# ---------------------------------------------------------------------------


def apply_fix(fix: dict) -> bool:
    """Apply a code fix to the working tree. Returns True on success."""
    file_path = REPO_ROOT / fix["file"]
    if not file_path.exists():
        print(f"  File not found: {fix['file']}")
        return False

    content = file_path.read_text()
    old_text = fix["old_text"]
    new_text = fix["new_text"]

    if old_text not in content:
        print(f"  old_text not found in {fix['file']}")
        return False

    updated = content.replace(old_text, new_text, 1)
    file_path.write_text(updated)
    print(f"  Applied fix to {fix['file']}")
    return True


def revert_fix(fix: dict) -> None:
    """Revert a previously applied fix."""
    file_path = REPO_ROOT / fix["file"]
    if not file_path.exists():
        return
    content = file_path.read_text()
    updated = content.replace(fix["new_text"], fix["old_text"], 1)
    file_path.write_text(updated)


def run_tests(scraper_name: Optional[str] = None) -> tuple[bool, str]:
    """Run the test suite. Returns (passed, output)."""
    # Run targeted tests first if we know the scraper
    if scraper_name:
        snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", scraper_name).lower()
        test_file = f"tests/test_{snake}_scraper_unit.py"
        if (REPO_ROOT / test_file).exists():
            result = subprocess.run(
                [str(REPO_ROOT / ".venv/bin/python"), "-m", "pytest", test_file, "-q"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=120,
            )
            if result.returncode != 0:
                return False, result.stdout + result.stderr

    # Run the full suite
    result = subprocess.run(
        [
            str(REPO_ROOT / ".venv/bin/python"),
            "-m",
            "pytest",
            "-q",
            "-m",
            "not live and not integration",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=300,
    )
    passed = result.returncode == 0
    return passed, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# PR creation
# ---------------------------------------------------------------------------


def create_fix_pr(
    diagnosis: str,
    fix: dict,
    scraper_name: Optional[str],
    issue_number: Optional[int],
) -> Optional[str]:
    """Create a branch, commit the fix, push, and open a PR."""
    branch = f"self-heal/fix-{scraper_name or 'pipeline'}-{os.getpid()}"

    # Configure git
    subprocess.run(
        ["git", "config", "user.name", "Culture-Calendar-Bot"],
        cwd=REPO_ROOT,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "bot@culture-calendar"],
        cwd=REPO_ROOT,
        check=True,
    )

    # Create branch
    subprocess.run(
        ["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True
    )

    # Commit
    subprocess.run(
        ["git", "add", fix["file"]], cwd=REPO_ROOT, check=True
    )
    msg = (
        f"fix({scraper_name or 'pipeline'}): auto-heal - {diagnosis[:80]}\n\n"
        f"Diagnosis: {diagnosis}\n\n"
        f"Auto-generated by the self-healing agent."
    )
    if issue_number:
        msg += f"\nCloses #{issue_number}"
    subprocess.run(
        ["git", "commit", "-m", msg], cwd=REPO_ROOT, check=True
    )

    # Push
    subprocess.run(
        ["git", "push", "origin", branch], cwd=REPO_ROOT, check=True
    )

    # Create PR
    resp = requests.post(
        f"{GITHUB_API}/repos/{REPO}/pulls",
        headers=_gh_headers(),
        json={
            "title": f"🔧 Auto-fix: {scraper_name or 'pipeline'} - {diagnosis[:60]}",
            "body": (
                f"## Self-healing agent fix\n\n"
                f"**Diagnosis**: {diagnosis}\n\n"
                f"**File changed**: `{fix['file']}`\n\n"
                f"This PR was auto-generated by the self-healing agent in response "
                f"to a pipeline failure. Review and merge if the fix looks correct."
                + (f"\n\nCloses #{issue_number}" if issue_number else "")
            ),
            "head": branch,
            "base": "main",
        },
        timeout=15,
    )
    if resp.ok:
        pr_url = resp.json()["html_url"]
        print(f"  Created PR: {pr_url}")
        return pr_url
    else:
        print(f"  Failed to create PR: {resp.status_code} {resp.text[:500]}")
        return None


# ---------------------------------------------------------------------------
# Health check (content freshness)
# ---------------------------------------------------------------------------


def health_check() -> list[dict]:
    """Check for content freshness issues.

    Returns a list of issues found, e.g.:
        [{"type": "stale_data", "detail": "data.json last updated 3 days ago"}]
    """
    issues = []

    # Check data.json freshness
    data_path = REPO_ROOT / "docs" / "data.json"
    if data_path.exists():
        import time

        mtime = data_path.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours > 48:
            issues.append(
                {
                    "type": "stale_data",
                    "detail": f"data.json is {age_hours:.0f} hours old (threshold: 48h)",
                }
            )

    # Check per-venue event counts
    if data_path.exists():
        data = json.loads(data_path.read_text())
        events = data if isinstance(data, list) else data.get("events", [])
        from datetime import date

        today = str(date.today())
        upcoming = [e for e in events if any(d >= today for d in e.get("dates", []))]

        venue_counts: dict[str, int] = {}
        for e in upcoming:
            v = e.get("venue", "?")
            venue_counts[v] = venue_counts.get(v, 0) + 1

        # Check for venues with zero upcoming events
        known_venues = [
            "AFS",
            "Paramount",
            "Hyperreal",
            "AlienatedMajesty",
            "FirstLight",
            "Symphony",
            "Opera",
            "BalletAustin",
            "IshidaDance",
        ]
        for v in known_venues:
            if venue_counts.get(v, 0) == 0:
                issues.append(
                    {
                        "type": "empty_venue",
                        "detail": f"{v} has 0 upcoming events",
                    }
                )

    return issues


def report_health_issues(issues: list[dict]) -> None:
    """Create or update a GitHub issue for health check findings."""
    if not issues:
        print("Health check passed - no issues found")
        return

    body = "## Automated Health Check\n\n"
    body += "The following issues were detected:\n\n"
    for issue in issues:
        body += f"- **{issue['type']}**: {issue['detail']}\n"
    body += "\n*This issue was auto-generated by the self-healing agent.*"

    # Check for existing open health issue
    resp = requests.get(
        f"{GITHUB_API}/repos/{REPO}/issues",
        headers=_gh_headers(),
        params={"labels": "health-check", "state": "open"},
        timeout=15,
    )
    existing = resp.json() if resp.ok else []

    if existing:
        # Comment on existing issue
        requests.post(
            f"{GITHUB_API}/repos/{REPO}/issues/{existing[0]['number']}/comments",
            headers=_gh_headers(),
            json={"body": body},
            timeout=15,
        )
        print(f"  Updated health issue #{existing[0]['number']}")
    else:
        # Create label + issue
        requests.post(
            f"{GITHUB_API}/repos/{REPO}/labels",
            headers=_gh_headers(),
            json={
                "name": "health-check",
                "color": "fbca04",
                "description": "Automated content freshness check",
            },
            timeout=15,
        )
        resp = requests.post(
            f"{GITHUB_API}/repos/{REPO}/issues",
            headers=_gh_headers(),
            json={
                "title": "⚠️ Content freshness issues detected",
                "body": body,
                "labels": ["health-check"],
            },
            timeout=15,
        )
        if resp.ok:
            print(f"  Created health issue #{resp.json()['number']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", type=int, help="Heal from a pipeline-failure issue")
    parser.add_argument("--run", help="Heal from a workflow run ID")
    parser.add_argument(
        "--health-check", action="store_true", help="Run content freshness check"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Diagnose only, don't apply fixes or create PRs",
    )
    args = parser.parse_args(argv)

    if args.health_check:
        issues = health_check()
        if issues:
            for i in issues:
                print(f"  {i['type']}: {i['detail']}")
            if not args.dry_run:
                report_health_issues(issues)
        else:
            print("All healthy")
        return 0

    # Determine run ID
    run_id = args.run
    issue_number = args.issue

    if args.issue:
        issue = fetch_issue(args.issue)
        run_id = extract_run_id_from_issue(issue.get("body", ""))
        if not run_id:
            print(f"No workflow run URL found in issue #{args.issue}")
            return 1

    if not run_id:
        print("Provide --issue or --run")
        return 1

    # Fetch logs
    print(f"Fetching logs for run {run_id}...")
    logs = fetch_run_logs(run_id)
    print(f"  Got {len(logs)} chars of log excerpts")

    # Identify failing component
    scraper_name = identify_failing_scraper(logs)
    print(f"  Failing component: {scraper_name or '(unknown)'}")

    # Read scraper code
    scraper_code = None
    scraper_file = None
    if scraper_name:
        path = find_scraper_file(scraper_name)
        if path:
            scraper_code = path.read_text()
            scraper_file = str(path.relative_to(REPO_ROOT))
            print(f"  Scraper file: {scraper_file}")

    # Diagnose + fix
    client = _claude_client()
    previous_error = ""

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        print(f"\nDiagnosis attempt {attempt}/{MAX_FIX_ATTEMPTS}...")
        result = diagnose_and_fix(
            client,
            logs,
            scraper_name,
            scraper_code,
            scraper_file,
            attempt=attempt,
            previous_error=previous_error,
        )

        print(f"  Diagnosis: {result['diagnosis']}")
        print(f"  Confidence: {result.get('confidence', '?')}")

        if not result.get("fix"):
            print("  No code fix suggested (transient issue or needs human review)")
            if args.issue and not args.dry_run:
                # Comment on the issue with the diagnosis
                requests.post(
                    f"{GITHUB_API}/repos/{REPO}/issues/{args.issue}/comments",
                    headers=_gh_headers(),
                    json={
                        "body": (
                            f"## 🤖 Self-healing agent diagnosis\n\n"
                            f"{result['diagnosis']}\n\n"
                            f"**Confidence**: {result.get('confidence', '?')}\n\n"
                            f"No automatic fix was generated. This may be a transient "
                            f"issue (site down, rate limit) or may need manual review."
                        )
                    },
                    timeout=15,
                )
            return 0

        if args.dry_run:
            print(f"  [DRY RUN] Would apply fix to {result['fix']['file']}")
            return 0

        # Apply fix
        print(f"  Applying fix to {result['fix']['file']}...")
        if not apply_fix(result["fix"]):
            print("  Fix application failed")
            previous_error = "old_text not found in file"
            continue

        # Run tests
        print("  Running tests...")
        passed, output = run_tests(scraper_name)
        if passed:
            print("  Tests passed! Creating PR...")
            pr_url = create_fix_pr(
                result["diagnosis"], result["fix"], scraper_name, issue_number
            )
            if pr_url and args.issue:
                requests.post(
                    f"{GITHUB_API}/repos/{REPO}/issues/{args.issue}/comments",
                    headers=_gh_headers(),
                    json={
                        "body": (
                            f"## 🤖 Self-healing agent fix\n\n"
                            f"**Diagnosis**: {result['diagnosis']}\n\n"
                            f"**Fix PR**: {pr_url}\n\n"
                            f"Tests passed. Review and merge the PR to resolve this issue."
                        )
                    },
                    timeout=15,
                )
            return 0
        else:
            print("  Tests failed, reverting fix...")
            revert_fix(result["fix"])
            # Extract test failure summary for next attempt
            previous_error = output[-2000:]

    print(f"\nAll {MAX_FIX_ATTEMPTS} fix attempts failed. Needs human review.")
    if args.issue and not args.dry_run:
        requests.post(
            f"{GITHUB_API}/repos/{REPO}/issues/{args.issue}/comments",
            headers=_gh_headers(),
            json={
                "body": (
                    f"## 🤖 Self-healing agent\n\n"
                    f"Attempted {MAX_FIX_ATTEMPTS} fixes but tests failed each time. "
                    f"Manual review needed.\n\n"
                    f"**Diagnosis**: {result['diagnosis']}"
                )
            },
            timeout=15,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
