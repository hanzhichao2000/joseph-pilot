import re
import sys
from pathlib import Path

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
PATH = re.compile(rf"{SLUG}/chapter-[0-9]{{2}}-{SLUG}/{SLUG}\.ipynb")
FIELDS = ("publication", "edition", "chapter", "published parameters")


def main(root: Path, strategies: Path | None = None) -> int:
    errors = []
    for directory in (root, strategies):
        if directory is not None and not directory.is_dir():
            errors.append(f"missing source root: {directory}")
    notebooks = list(root.rglob("*.ipynb")) if root.is_dir() else []
    modules = (
        [path for path in strategies.rglob("*.py") if path.name != "__init__.py"]
        if strategies is not None and strategies.is_dir()
        else []
    )
    for notebook in notebooks:
        if not PATH.fullmatch(notebook.relative_to(root).as_posix()):
            errors.append(f"invalid notebook path: {notebook}")
    for item in notebooks + modules:
        source = item.parent / "SOURCE.md"
        if not source.is_file():
            errors.append(f"missing SOURCE.md: {item}")
            continue
        text = source.read_text(encoding="utf-8")
        for field in FIELDS:
            match = re.search(rf"(?im)^[^\S\r\n]*{re.escape(field)}[^\S\r\n]*:([^\r\n]*)", text)
            value = match.group(1).strip() if match else ""
            if not value or value.casefold() in {
                "todo",
                "tbd",
                "placeholder",
                "unknown",
                "n/a",
                "<required>",
            }:
                errors.append(f"missing or placeholder {field}: {source}")
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main(Path("notebooks/book-examples"), Path("src/joseph_pilot/strategies")))
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
