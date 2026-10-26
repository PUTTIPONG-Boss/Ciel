"""Auto-update: poll GitHub, fast-forward, and restart only when needed.

- web/, persona/, docs/ changes apply live (the page reloads itself)
- ciel/ or requirements.txt changes → pip install if needed, then exit;
  launchd (KeepAlive) starts Ciel again with the new code

Never touches a working tree with local edits or commits that aren't on GitHub.
"""

import asyncio
import logging
import os
import shutil
import signal
import sys
from typing import Callable

from .config import ROOT, settings

log = logging.getLogger("ciel.updater")

RESTART_PATHS = ("ciel/", "requirements.txt")
GIT = shutil.which("git") or next((p for p in ("/opt/homebrew/bin/git", "/usr/bin/git") if os.path.exists(p)), "git")


async def _run(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="ignore").strip()


async def _git(*args: str) -> tuple[int, str]:
    return await _run(GIT, *args)


async def check_once() -> bool:
    """Pull new commits if possible. Returns True when a restart is needed."""
    code, out = await _git("fetch", "--quiet", "origin", settings.update_branch)
    if code:
        log.warning("git fetch failed: %s", out)
        return False

    _, local = await _git("rev-parse", "HEAD")
    _, remote = await _git("rev-parse", "FETCH_HEAD")
    if local == remote:
        return False

    if (await _git("merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD"))[0]:
        log.warning("local commits not on GitHub — skipping auto-update")
        return False
    if (await _git("status", "--porcelain", "--untracked-files=no"))[1]:
        log.warning("local file edits present — skipping auto-update")
        return False

    _, changed = await _git("diff", "--name-only", "HEAD", "FETCH_HEAD")
    code, out = await _git("merge", "--ff-only", "--quiet", "FETCH_HEAD")
    if code:
        log.warning("git merge failed: %s", out)
        return False

    files = changed.splitlines()
    log.info("updated %s → %s (%d files)", local[:7], remote[:7], len(files))

    if "requirements.txt" in files:
        code, out = await _run(sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt")
        if code:
            log.error("pip install failed: %s", out)

    return any(f.startswith(RESTART_PATHS) for f in files)


async def run_forever(is_idle: Callable[[], bool]) -> None:
    log.info("auto-update on: checking origin/%s every %ss", settings.update_branch, settings.update_interval)
    while True:
        await asyncio.sleep(settings.update_interval)
        try:
            if not await check_once():
                continue
        except Exception:
            log.exception("auto-update check failed")
            continue

        # Let Ciel finish the sentence she's on (up to 5 min) before restarting
        for _ in range(300):
            if is_idle():
                break
            await asyncio.sleep(1)
        log.info("restarting to load new code")
        os.kill(os.getpid(), signal.SIGTERM)
        return
