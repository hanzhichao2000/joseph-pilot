"""Check tracked paths and text for markers from a publishable keyword list."""

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path


def load_terms(keywords: Path) -> tuple[str, ...]:
    terms = tuple(
        line.strip().casefold()
        for line in keywords.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not terms:
        raise ValueError("no effective terms")
    return terms


def tracked_paths(root: Path) -> list[str]:
    if subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--show-prefix"],
        stderr=subprocess.DEVNULL,
    ).strip():
        raise ValueError("not a repository root")
    paths = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"],
        stderr=subprocess.DEVNULL,
    )
    return list(dict.fromkeys(os.fsdecode(path) for path in paths.split(b"\0") if path))


def read_text(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            return os.readlink(path)
        if not stat.S_ISREG(mode):
            return ""
        data = path.read_bytes()
    except FileNotFoundError:
        # A staged path can be deleted from the working tree during local review.
        return ""
    if b"\0" in data:
        return ""
    return data.decode("utf-8", errors="ignore")


def check(keywords: Path, root: Path) -> int:
    try:
        terms = load_terms(keywords)
    except (OSError, UnicodeError, ValueError):
        print("public keyword list missing, unreadable, or empty", file=sys.stderr)
        return 2

    try:
        root = root.resolve()
        keywords = keywords.resolve()
        names = tracked_paths(root)
        path_matches = text_matches = 0
        for name in names:
            path = root / name
            path_matches += any(term in f"/{name.casefold()}" for term in terms)
            # The policy file defines the publishable markers and can contain them.
            if path == keywords:
                continue
            text = read_text(path).casefold()
            text_matches += any(term in text for term in terms)
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("cannot scan the target Git working tree", file=sys.stderr)
        return 2

    if path_matches or text_matches:
        print(
            f"public keyword check failed ({path_matches} path, {text_matches} text matches)",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keywords", type=Path)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    return check(args.keywords, args.root)


if __name__ == "__main__":
    sys.exit(main())
