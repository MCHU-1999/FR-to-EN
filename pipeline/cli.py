"""fr2en: parse → translate → render a saved French documentation page.

    uv run fr2en sources/batiment-bduni                 # full pipeline -> output/batiment-bduni.en.pdf
    uv run fr2en sources/batiment-bduni --dry-run       # count DeepL characters, send nothing
    uv run fr2en sources/batiment-bduni --lang fr       # render the French original (no DeepL)
    uv run fr2en sources/batiment-bduni --stage parse   # run a single stage
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import parse, render, translate

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file. Variables already set in the shell win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            os.environ.setdefault(key.strip(), value)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fr2en", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="folder holding the saved page (src.html + its files)")
    ap.add_argument("--stage", choices=["parse", "translate", "render", "all"], default="all")
    ap.add_argument("--lang", choices=["en", "fr"], default="en", help="which language to render (default: en)")
    ap.add_argument("--dry-run", action="store_true", help="parse + count DeepL characters, send nothing")
    ap.add_argument("--accent", default="#7AA43E", help="template accent colour (default: %(default)s)")
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")

    src = args.source.resolve()
    slug = src.name
    build = ROOT / "build" / slug
    fr_json, en_json = build / "doc.fr.json", build / "doc.en.json"

    if args.stage in ("parse", "all") or (args.dry_run and not fr_json.exists()):
        parse.run(src, build, ROOT)
    if args.dry_run:
        translate.run(fr_json, en_json, ROOT, dry_run=True)
        return
    if args.stage in ("translate", "all") and args.lang == "en":
        translate.run(fr_json, en_json, ROOT)
    if args.stage in ("render", "all"):
        doc = fr_json if args.lang == "fr" else en_json
        if not doc.exists():
            raise SystemExit(f"{doc} missing – run the earlier stages first")
        render.run(doc, ROOT / "output" / f"{slug}.{args.lang}.pdf", ROOT, args.accent)


if __name__ == "__main__":
    main()
