"""Turn doc.<lang>.json into a Typst-ready JSON (inline HTML -> styled runs) and compile the PDF."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

UI = {
    "en": {"code": "IGN · BDUni", "subtitle": "English translation",
           "author": "Translated from French with DeepL", "date_label": "Translated", "source_label": "Source"},
    "fr": {"code": "IGN · BDUni", "subtitle": "Version originale",
           "author": "IGN – Service vecteur et 3D", "date_label": "Généré le", "source_label": "Source"},
}

# Relative column widths for the 7-column "detailed attribute table".
SUMMARY_TABLE_WIDTHS = [1.7, 1.1, 1.5, 1.25, 0.6, 0.7, 2.2]


class _Runs(HTMLParser):
    FLAGS = {"i": "i", "em": "i", "b": "b", "strong": "b", "u": "u", "code": "code"}

    def __init__(self, labels: set[str]):
        super().__init__(convert_charrefs=True)
        self.labels = labels
        self.stack: list[tuple[str, str | None]] = []
        self.runs: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.runs.append({"br": True})
            return
        href = dict(attrs).get("href") if tag == "a" else None
        if href and href.startswith("#") and href[1:] not in self.labels:
            href = None  # dangling internal anchor -> plain text
        self.stack.append((tag, href))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i]
                break

    def handle_data(self, data):
        if not data:
            return
        run: dict = {"t": data}
        for tag, href in self.stack:
            if flag := self.FLAGS.get(tag):
                run[flag] = True
            if href:
                run["href"] = href
        prev = self.runs[-1] if self.runs else None
        if prev and "br" not in prev and {k: v for k, v in prev.items() if k != "t"} == \
                {k: v for k, v in run.items() if k != "t"}:
            prev["t"] += data
        else:
            self.runs.append(run)


def runs(html_str: str, labels: set[str]) -> list[dict]:
    p = _Runs(labels)
    p.feed(html_str or "")
    p.close()
    return p.runs


def _block(b: dict, labels: set[str]) -> dict:
    t = b["type"]
    R = lambda s: runs(s, labels)  # noqa: E731
    if t == "para":
        return {"type": t, "runs": R(b["html"])}
    if t == "list":
        return {"type": t, "items": [R(i) for i in b["items"]]}
    if t == "meta":
        return {"type": t, "items": [{"label": i["label"], "runs": R(i["html"])} for i in b["items"]]}
    if t == "article":
        return {"type": t, "label": b["label"], "blocks": [_block(c, labels) for c in b["blocks"]]}
    if t == "table":
        out = {"type": t, "header": [R(h) for h in b["header"]],
               "rows": [[R(c) for c in row] for row in b["rows"]], "caption": R(b.get("caption", ""))}
        if b.get("widths"):
            out["widths"] = b["widths"]
        return out
    if t == "figure":
        return {"type": t, "src": b["src"], "ref": b["ref"], "caption": R(b.get("caption", ""))}
    raise ValueError(f"unknown block type {t!r}")


def to_render_json(doc: dict) -> dict:
    labels = {s["label"] for s in doc["sections"] if s.get("label")}
    sections = []
    for s in doc["sections"]:
        blocks = [_block(b, labels) for b in s["blocks"]]
        if s.get("label") == "attr-table":
            for b in blocks:
                if b["type"] == "table" and len(b["header"]) == len(SUMMARY_TABLE_WIDTHS):
                    b["widths"] = SUMMARY_TABLE_WIDTHS
        heading = "".join(r.get("t", "") for r in runs(s["heading"], labels)).strip()
        sections.append({"heading": heading, "level": s["level"], "label": s["label"], "blocks": blocks})
    lang = doc.get("lang", "en")
    return {"lang": lang, "title": doc["title"], "series": doc["series"],
            "source_url": doc["source_url"], "ui": UI.get(lang, UI["en"]), "sections": sections}


def run(doc_json: Path, pdf_out: Path, root: Path, accent: str = "#7AA43E") -> Path:
    if not shutil.which("typst"):
        raise SystemExit("typst not found on PATH")
    doc = json.loads(doc_json.read_text(encoding="utf-8"))
    render_json = doc_json.with_name(f"render.{doc.get('lang', 'en')}.json")
    render_json.write_text(json.dumps(to_render_json(doc), ensure_ascii=False), encoding="utf-8")

    pdf_out.parent.mkdir(parents=True, exist_ok=True)
    data_path = "/" + render_json.resolve().relative_to(root.resolve()).as_posix()
    cmd = ["typst", "compile", str(root / "typst" / "doc.typ"), str(pdf_out),
           "--root", str(root), "--font-path", str(root / "fonts"),
           "--input", f"data={data_path}", "--input", f"accent={accent}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stderr.strip():
        print(res.stderr.strip(), file=sys.stderr)
    if res.returncode != 0:
        raise SystemExit(f"[render] typst failed ({res.returncode})")
    print(f"[render] {pdf_out}")
    return pdf_out
