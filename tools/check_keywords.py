import os
import sys
from pathlib import Path

LISTS = ("private-paths.txt", "proprietary-strategies.txt", "vendor.txt")
EXCLUDED = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".boundary-docs",
}


def main(keywords: Path, root: Path) -> int:
    if not root.is_dir():
        print("scan root is missing or not a directory", file=sys.stderr)
        return 1
    terms = []
    for name in LISTS:
        path = keywords / name
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            print(f"keyword list unavailable: {name}", file=sys.stderr)
            return 1
        current = [
            line.strip().casefold()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not current:
            print(f"keyword list empty: {name}", file=sys.stderr)
            return 1
        terms.extend(current)
    failed = False
    for directory, dirs, files in os.walk(root):
        dirs[:] = [
            name
            for name in dirs
            if name not in EXCLUDED
            and not name.endswith(".egg-info")
            and not name.endswith(".cache")
        ]
        for name in files:
            path = Path(directory) / name
            if name == ".git" or path.is_symlink():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                print(f"cannot scan: {path}", file=sys.stderr)
                failed = True
                continue
            if b"\0" in data:
                continue
            try:
                content = data.decode("utf-8").casefold()
            except UnicodeDecodeError:
                continue
            if any(term in content for term in terms):
                print(f"keyword match: {path}", file=sys.stderr)
                failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()))
