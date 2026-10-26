"""Which build is running. Read from disk on every call (cheap), so an
auto-update that only touches web/ still reports the new version without a restart."""

from .config import ROOT


def version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def commit() -> str:
    """Short hash of HEAD, read straight from .git (no git binary needed)."""
    git = ROOT / ".git"
    try:
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head[5:]
        if (git / ref).exists():
            return (git / ref).read_text().strip()[:7]
        for line in (git / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line[:7]
    except OSError:
        pass
    return ""


def info() -> dict:
    return {"version": version(), "commit": commit()}
