"""Update service - check GitHub for newer versions and guide the user to update.

Two check strategies, in order of preference:
1. GitHub Releases (preferred) - uses the 'latest' release tag
2. Git commit comparison (fallback) - counts commits behind origin/main

The service never modifies the filesystem. It only reports. The user is
responsible for running `git pull` and restarting Claude Code.
"""

import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from memory_mcp import __version__

GITHUB_OWNER = "serkansmg"
GITHUB_REPO = "smg-claude-memory-mcp"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
HTTP_TIMEOUT = 5


def _find_install_dir() -> Path | None:
    """Locate the install directory by walking up from this source file."""
    try:
        # This file: src/memory_mcp/services/update_service.py
        here = Path(__file__).resolve()
        install_dir = here.parent.parent.parent.parent  # up to repo root
        if (install_dir / "pyproject.toml").exists():
            return install_dir
    except Exception:
        pass
    return None


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd),
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def _fetch_github_json(path: str) -> dict | None:
    """GET a GitHub API endpoint. Returns parsed JSON or None on failure."""
    url = f"{GITHUB_API_BASE}{path}"
    req = Request(url, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"memory-mcp/{__version__}",
    })
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def _parse_semver(tag: str) -> tuple[int, int, int] | None:
    """Parse 'v1.2.3' or '1.2.3' → (1, 2, 3). Returns None on failure."""
    s = tag.lstrip("v").strip()
    parts = s.split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except ValueError:
        return None


def _version_tuple_gt(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    return a > b


class UpdateService:
    """Check for newer versions and present a clear update path."""

    def check(self) -> dict:
        """Returns a structured update check result.

        Keys:
          - current_version: from __init__.py
          - source: 'github_releases' or 'git' or 'unknown'
          - update_available: bool
          - latest_version: str (semver if from releases, else commit sha)
          - commits_behind: int (if source is 'git')
          - release_url: str | None
          - release_notes: str | None (excerpt)
          - recent_commits: list[str] (if source is 'git')
          - install_dir: str | None
          - how_to_update: list[str] (step-by-step)
          - warnings: list[str]
        """
        current = __version__
        install_dir = _find_install_dir()

        result: dict = {
            "current_version": current,
            "source": "unknown",
            "update_available": False,
            "install_dir": str(install_dir) if install_dir else None,
            "warnings": [],
        }

        # Try GitHub Releases first
        release_result = self._check_via_release(current)
        if release_result is not None:
            result.update(release_result)
            result["source"] = "github_releases"
        else:
            # Fallback: git commit comparison
            git_result = self._check_via_git(install_dir)
            if git_result is not None:
                result.update(git_result)
                result["source"] = "git"
            else:
                result["warnings"].append(
                    "Could not check for updates (no network or git repository unavailable)"
                )

        # Compose how-to-update steps
        if result.get("update_available"):
            result["how_to_update"] = self._build_update_steps(install_dir, result.get("source"))
        else:
            result["how_to_update"] = []

        return result

    def _check_via_release(self, current_version: str) -> dict | None:
        """Check the latest GitHub release. Returns dict or None if no release."""
        data = _fetch_github_json("/releases/latest")
        if data is None:
            return None

        tag = data.get("tag_name", "")
        latest_semver = _parse_semver(tag)
        current_semver = _parse_semver(current_version)

        if latest_semver is None or current_semver is None:
            return None

        update_available = _version_tuple_gt(latest_semver, current_semver)

        # Truncate release body
        body = data.get("body", "") or ""
        if len(body) > 1000:
            body = body[:1000] + "\n...(truncated)"

        return {
            "latest_version": tag.lstrip("v"),
            "update_available": update_available,
            "release_url": data.get("html_url"),
            "release_notes": body or None,
            "release_published_at": data.get("published_at"),
        }

    def _check_via_git(self, install_dir: Path | None) -> dict | None:
        """Compare local HEAD to origin/main. Returns dict or None."""
        if install_dir is None or not (install_dir / ".git").exists():
            return None

        # Get current commit
        code, current_sha, _ = _run_git(["rev-parse", "--short", "HEAD"], install_dir)
        if code != 0:
            return None

        # Fetch latest remote refs (quiet)
        fetch_code, _, fetch_err = _run_git(["fetch", "--quiet", "origin"], install_dir)
        if fetch_code != 0:
            return {
                "latest_version": current_sha,
                "update_available": False,
                "warnings_extra": [f"git fetch failed: {fetch_err}"],
            }

        # Count commits behind
        code, behind_count, _ = _run_git(
            ["rev-list", "--count", "HEAD..origin/main"], install_dir,
        )
        if code != 0:
            return None
        try:
            commits_behind = int(behind_count)
        except ValueError:
            commits_behind = 0

        # Get remote HEAD sha
        _, remote_sha, _ = _run_git(["rev-parse", "--short", "origin/main"], install_dir)

        # Get commit messages we'd pull
        recent_commits: list[str] = []
        if commits_behind > 0:
            _, log_out, _ = _run_git(
                ["log", "--oneline", f"HEAD..origin/main", "-n", "10"], install_dir,
            )
            if log_out:
                recent_commits = [line.strip() for line in log_out.splitlines() if line.strip()]

        return {
            "latest_version": remote_sha or current_sha,
            "update_available": commits_behind > 0,
            "commits_behind": commits_behind,
            "recent_commits": recent_commits,
            "current_commit": current_sha,
            "latest_commit": remote_sha,
        }

    def _build_update_steps(self, install_dir: Path | None, source: str | None) -> list[str]:
        """Generate step-by-step update instructions."""
        install_path = str(install_dir) if install_dir else "/path/to/memory-mcp"

        steps = [
            f"1. Open a terminal and navigate to the install directory:",
            f"   cd {install_path}",
            "2. Pull the latest changes:",
            "   git pull origin main",
            "3. Update Python dependencies (in case requirements changed):",
            "   uv sync",
            "4. Restart Claude Code to load the new MCP server version.",
            "5. Verify with memory_version() - it should show the new version.",
        ]

        if source == "github_releases":
            steps.insert(0, "(This update was detected from a GitHub release.)")

        return steps
