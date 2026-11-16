# FR-to-EN
A vault to store and translate technical documents from French to English.

Saved French documentation pages are parsed into structured JSON, translated with
DeepL (glossary + translation cache), and typeset with Typst into a document-style PDF
(template: a vendored, relabelled copy of `breezy-report` 0.1.0).

```
sources/<slug>/src.html ─parse─▶ build/<slug>/doc.fr.json ─DeepL─▶ doc.en.json ─Typst─▶ output/<slug>.en.pdf
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and [Typst](https://typst.app) ≥ 0.13 on `PATH`.

```sh
uv sync                                  # installs into .venv (Python 3.13)
cp .env.example .env                     # then put your DeepL API Free key (ends in :fx) in .env
```

`.env` is gitignored. A `DEEPL_AUTH_KEY` already exported in the shell takes precedence over it.

## Usage

```sh
uv run fr2en sources/batiment-bduni --dry-run   # characters that would be sent to DeepL + remaining quota
uv run fr2en sources/batiment-bduni             # parse → translate → output/batiment-bduni.en.pdf
uv run fr2en sources/batiment-bduni --lang fr   # typeset the French original (no DeepL)
uv run fr2en sources/batiment-bduni --stage render --accent "#1B3A6B"   # re-render only, other colour
```

## Adding a document

1. In the browser, *Save Page As → Web Page, complete* and put the `.html` plus its files in
   `sources/<slug>/` (rename the page to `src.html`). `sources/` is gitignored on purpose: saved
   pages can contain session cookies and server debug output. The parser reads only the
   documentation container, so none of that ends up in `build/` or the PDF.
2. `uv run fr2en sources/<slug> --dry-run`, then without `--dry-run`.
3. Add recurring terms to `glossary.csv`. Changing it creates a new DeepL glossary and
   re-translates the strings (the cache is keyed on the glossary).

The parser (`pipeline/parse.py`) understands IGN BDUni documentation pages
(`div.div_accueil`, `div.div_attribut`, …). Other kinds of source need their own parser that
emits the same JSON block format.

## Layout

| Path | |
|---|---|
| `pipeline/` | `parse.py`, `translate.py`, `render.py`, `cli.py` |
| `typst/breezy.typ` | vendored template (MIT, see `typst/LICENSE-breezy-report`) |
| `typst/doc.typ` | turns the JSON into the document |
| `fonts/` | Montserrat (OFL); body font Libertinus Serif is built into Typst |
| `glossary.csv` | FR → EN terminology sent to DeepL |
| `cache/translations.jsonl` | translation memory: re-runs cost 0 DeepL characters |
| `output/` | generated PDFs |
