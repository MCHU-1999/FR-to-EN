"""Parse a saved IGN BDUni documentation page into a structured JSON document.

Only the documentation container (``div.div_accueil``) is read. The PHP debug
dump (session cookies, server info) and site chrome around it are never touched.

Output shape (doc.fr.json)::

    {"lang": "fr", "title", "series", "source_url", "id_classe",
     "sections": [{"heading", "level", "label", "blocks": [...]}]}

Block types: para, list, table, figure, meta, article (label + nested blocks).
Inline text is a small HTML subset: <i> <b> <u> <code> <br> <a href>.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

BASE_URL = "https://pomme.ign.fr/SV3D/Documentation-BDUni-v2/"

INLINE_TAGS = {"i": "i", "em": "i", "b": "b", "strong": "b", "u": "u", "code": "code"}
CONTAINER_TAGS = {"center", "div", "p", "tbody", "thead", "span", "font"}
BULLET_RE = re.compile(r"^\s*[•\-–·]\s*")
FIG_PREFIX_RE = re.compile(r"^\s*Fig(?:ure)?\.?\s*\d+\s*[:.\-–]?\s*", re.I)


# --------------------------------------------------------------------------- inline


def _drop(tag: Tag) -> bool:
    cls = set(tag.get("class", []))
    return (
        tag.name in {"script", "style", "img"}
        or bool(cls & {"copier_lien_attribut", "copier_lien_valeur", "copier_lien_classe", "titre_article"})
        or tag.get("style", "").replace(" ", "") == "display:none;"
    )


def _href(href: str) -> str:
    if m := re.fullmatch(r"#attribute_value_(\d+)", href):
        return f"#val-{m[1]}"
    if m := re.fullmatch(r"#attribute_(\d+)", href):
        return f"#attr-{m[1]}"
    return urljoin(BASE_URL, href)


def inline_html(node) -> str:
    """Serialise a node into the restricted inline HTML subset."""
    if isinstance(node, NavigableString):
        if node.__class__.__name__ == "Comment":
            return ""
        return html.escape(re.sub(r"\s+", " ", str(node)), quote=False)
    if not isinstance(node, Tag) or _drop(node):
        return ""
    if node.name == "br":
        return "<br>"
    inner = "".join(inline_html(c) for c in node.children)
    if node.name in INLINE_TAGS:
        t = INLINE_TAGS[node.name]
        return f"<{t}>{inner}</{t}>" if inner.strip() else inner
    if node.name == "a" and node.get("href") and "magnific-popup" not in node.get("class", []):
        return f'<a href="{html.escape(_href(node["href"]))}">{inner}</a>'
    return inner


def text_of(html_str: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", html_str)).strip()


def tidy(html_str: str) -> str:
    """Collapse whitespace and trim leading/trailing <br>s."""
    s = re.sub(r"[ \t\r\n]+", " ", html_str)
    s = re.sub(r"\s*<br>\s*", "<br>", s)
    s = re.sub(r"^(?:<br>|\s)+|(?:<br>|\s)+$", "", s)
    return s.strip()


def code(s: str) -> str:
    s = s.strip()
    return f"<code>{html.escape(s, quote=False)}</code>" if s else ""


# --------------------------------------------------------------------------- blocks


class BlockWalker:
    """Turn mixed article content (text, <br>, tables, images) into blocks."""

    def __init__(self, ctx: "Context"):
        self.ctx = ctx
        self.buf: list[str] = []
        self.blocks: list[dict] = []

    def walk(self, node) -> list[dict]:
        self._visit(node, top=True)
        self._flush()
        return self.blocks

    def _visit(self, node, top=False):
        children = node.children if top else [node]
        for c in children:
            if isinstance(c, NavigableString):
                self.buf.append(inline_html(c))
            elif not isinstance(c, Tag):
                continue
            elif c.name == "table":
                self._flush()
                self.blocks.append(self.ctx.table(c))
            elif c.name in {"ul", "ol"}:
                self._flush()
                items = [tidy(inline_html(li)) for li in c.find_all("li")]
                if items := [i for i in items if i]:
                    self.blocks.append({"type": "list", "items": items})
            elif c.name == "img" and "image-article" in c.get("class", []):
                self._flush()
                self.blocks.append(self.ctx.figure(c))
            elif c.name == "a" and "magnific-popup" in c.get("class", []):
                for img in c.find_all("img", class_="image-article"):
                    self._flush()
                    self.blocks.append(self.ctx.figure(img))
            elif c.name in {"font", "center"} and not c.find("img") \
                    and (c.name == "font" or c.find("font")) \
                    and self.blocks and self.blocks[-1]["type"] == "figure" \
                    and not self.blocks[-1]["caption"] and not "".join(self.buf).replace("<br>", "").strip():
                # A small-font line right after an image is its caption.
                self.buf.clear()
                self.blocks[-1]["caption"] = FIG_PREFIX_RE.sub("", tidy(inline_html(c)).replace("<i>", "").replace("</i>", ""))
            elif _drop(c):
                continue
            elif c.name in CONTAINER_TAGS and c.find(["table", "img", "ul", "ol", "div", "p"]):
                if c.name in {"div", "p"}:
                    self._flush()
                self._visit(c, top=True)
                if c.name in {"div", "p"}:
                    self._flush()
            elif c.name == "p":
                self._flush()
                self.buf.append(inline_html(c))
                self._flush()
            else:
                self.buf.append(inline_html(c))

    def _flush(self):
        raw = "".join(self.buf)
        self.buf.clear()
        raw = re.sub(r"[ \t\r\n]+", " ", raw)
        for para in re.split(r"(?:\s*<br>\s*){2,}", raw):
            lines = [tidy(l) for l in para.split("<br>")]
            lines = [l for l in lines if text_of(l)]
            group: list[str] = []
            kind = None
            for line in lines:
                is_bullet = bool(BULLET_RE.match(text_of(line)))
                k = "list" if is_bullet else "para"
                if k != kind and group:
                    self._emit(kind, group)
                    group = []
                kind = k
                group.append(re.sub(r"^\s*[•\-–·]\s*", "", line, count=1) if is_bullet else line)
            if group:
                self._emit(kind, group)

    def _emit(self, kind, lines):
        if kind == "list":
            self.blocks.append({"type": "list", "items": lines})
        else:
            self.blocks.append({"type": "para", "html": "<br>".join(lines)})


# --------------------------------------------------------------------------- context


class Context:
    def __init__(self, src_dir: Path, out_dir: Path, root: Path):
        self.src_dir = src_dir
        self.img_dir = out_dir / "img"
        self.root = root
        self.missing: list[str] = []
        self.figures = 0
        self.tables = 0

    def _find_image(self, ref: str) -> Path | None:
        name = Path(ref).name
        stem, ext = Path(name).stem, Path(name).suffix
        for cand in [self.src_dir / ref, self.src_dir / name]:
            if cand.is_file():
                return cand
        hits = sorted(p for p in self.src_dir.iterdir()
                      if p.suffix.lower() == ext.lower() and p.stem.startswith(stem + "_"))
        return hits[0] if hits else None

    def figure(self, img: Tag) -> dict:
        ref = img.get("src", "")
        self.figures += 1
        found = self._find_image(ref)
        block = {"type": "figure", "src": None, "ref": Path(ref).name, "caption": ""}
        if found:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(ref).name)
            self.img_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, self.img_dir / safe)
            block["src"] = "/" + (self.img_dir / safe).resolve().relative_to(self.root.resolve()).as_posix()
        else:
            self.missing.append(ref)
        return block

    def table(self, tbl: Tag, code_cols: dict[int, str] | None = None) -> dict:
        """code_cols: column index -> 'all' (whole cell is an identifier) or 'after-br'."""
        self.tables += 1
        code_cols = code_cols or {}
        rows = []
        header = None
        for tr in tbl.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if all(c.name == "th" for c in cells) and header is None and not rows:
                header = [tidy(inline_html(c)) for c in cells]
                continue
            row = []
            for i, c in enumerate(cells):
                mode = code_cols.get(i)
                if mode == "all":
                    row.append(code(c.get_text(" ", strip=True)))
                elif mode == "after-br" and c.find("br"):
                    br = c.find("br")
                    before = "".join(inline_html(s) for s in br.find_previous_siblings()[::-1])
                    after = "".join(s if isinstance(s, str) else s.get_text() for s in br.next_siblings)
                    row.append(tidy(before) + "<br>" + code(after))
                else:
                    row.append(tidy(inline_html(c)))
            rows.append(row)
        return {"type": "table", "header": header or [], "rows": rows, "caption": ""}


# --------------------------------------------------------------------------- articles


def article(div: Tag, ctx: Context) -> dict | None:
    title_el = div.find(class_="titre_article")
    label = title_el.get_text(" ", strip=True) if title_el else ""
    content = div.find(class_="contenu_article")
    if content is None:
        return None
    # The leading " : " after the title lives either inside the content div or between spans.
    blocks = BlockWalker(ctx).walk(content)
    if blocks and blocks[0]["type"] == "para":
        blocks[0]["html"] = re.sub(r"^\s*:\s*", "", blocks[0]["html"])
        if not text_of(blocks[0]["html"]):
            blocks.pop(0)
    if not blocks:
        return None
    return {"type": "article", "label": label, "blocks": blocks}


def attribute_section(attr: Tag, ctx: Context) -> list[dict]:
    num = attr["id"].removeprefix("attribute_")
    name = attr.select_one(".titre_attribut_pdf").get_text(" ", strip=True)
    meta = []
    if t := attr.select_one(".attribute_type"):
        meta.append({"label": "Type", "html": tidy(inline_html(t))})
    if d := attr.select_one(".attribute_diffusion"):
        products = d.get_text(" ", strip=True).removeprefix("Diffusion").strip()
        meta.append({"label": "Diffusion", "html": ", ".join(code(p) for p in products.split(","))})
    if fmt := attr.select_one("table.table_nom_attr"):
        heads = [th.get_text(" ", strip=True) for th in fmt.select("th")]
        cols: dict[int, list[str]] = {i: [] for i in range(len(heads))}
        for r, tr in enumerate(fmt.select("tr")[1:]):
            for i, td in enumerate(tr.find_all("td")):
                txt = td.get_text(" ", strip=True)
                if txt and i in cols:
                    cols[i].append(code(txt) if r == 0 else html.escape(txt, quote=False))
        for i, h in enumerate(heads):
            if cols[i]:
                meta.append({"label": h, "html": " — ".join(cols[i])})

    blocks: list[dict] = []
    if meta:
        blocks.append({"type": "meta", "items": meta})
    for div in attr.find_all("div", class_="un_article", recursive=False):
        if a := article(div, ctx):
            blocks.append(a)
    sections = [{"heading": name, "level": 2, "label": f"attr-{num}", "blocks": blocks}]

    for val in attr.find_all("div", class_="div_valeur", recursive=False):
        vnum = val["id"].removeprefix("attribute_value_")
        title = val.select_one(".titre_valeur")
        vblocks = [a for div in val.find_all("div", class_="un_article", recursive=False)
                   if (a := article(div, ctx))]
        sections.append({"heading": tidy(inline_html(title)), "level": 3,
                         "label": f"val-{vnum}", "blocks": vblocks})
    return sections


# --------------------------------------------------------------------------- document


def parse(src_html: Path, out_dir: Path, root: Path) -> tuple[dict, Context]:
    raw = src_html.read_text(encoding="utf-8")
    # The site prints placeholders like "<Zone de réconciliation" unescaped; stop
    # the HTML parser from treating them as tags (all real tags are lowercase).
    raw = re.sub(r"<(?=[A-ZÀ-Ý][a-zà-ÿ])", "&lt;", raw)
    # ...and sometimes double-escapes real tags, e.g. a literal "&lt;p&gt;".
    raw = re.sub(r"&lt;/?p&gt;", " ", raw)
    soup = BeautifulSoup(raw, "lxml")

    main = soup.select_one("div.div_accueil")
    if main is None:
        raise SystemExit(f"{src_html}: no div.div_accueil – not a BDUni documentation page?")

    ctx = Context(src_html.parent, out_dir, root)
    h1 = soup.select_one(".page-centree h1")
    page_title = h1.get_text(" ", strip=True) if h1 else ""
    feature = main.select_one(".titre_feature_type")
    title = feature.get_text(" ", strip=True) if feature else page_title.split(" - ")[0]
    series = page_title.split(" - ", 1)[1] if " - " in page_title else "Documentation BDUni"

    id_classe = None
    if (ft := main.select_one(".div_feature_type")) and ft.get("id"):
        id_classe = ft["id"].removeprefix("feature_type_")
    source_url = BASE_URL + (f"?id_classe={id_classe}" if id_classe else "")

    overview_meta: list[dict] = []
    overview_blocks: list[dict] = []
    table_section = None
    attr_sections: list[dict] = []

    for el in main.find_all(recursive=False):
        cls = set(el.get("class", []))
        if "type-geom" in cls:
            label = el.select_one(".titre_type_geom").get_text(" ", strip=True)
            value = el.get_text(" ", strip=True).removeprefix(label).lstrip(" :")
            overview_meta.append({"label": label, "html": html.escape(value, quote=False)})
        elif "un_article" in cls and el.find("table", class_="tableau"):
            tbl = ctx.table(el.find("table", class_="tableau"), {0: "after-br", 1: "all", 2: "all"})
            label = el.select_one(".titre_article").get_text(" ", strip=True)
            table_section = {"heading": label, "level": 1, "label": "attr-table", "blocks": [tbl]}
        elif "un_article" in cls and not el.get("id"):
            label = el.select_one(".titre_article").get_text(" ", strip=True)
            value = el.select_one(".contenu_article").get_text(" ", strip=True)
            overview_meta.append({"label": label, "html": code(value) if label != "Nom PostgreSQL"
                                  else code(value.split(" (")[0]) + html.escape(value[len(value.split(" (")[0]):])})
        elif "un_article" in cls:
            if a := article(el, ctx):
                overview_blocks.append(a)
        elif "div_attribut" in cls:
            attr_sections.extend(attribute_section(el, ctx))

    sections = [{"heading": "Présentation", "level": 1, "label": "overview",
                 "blocks": ([{"type": "meta", "items": overview_meta}] if overview_meta else []) + overview_blocks}]
    if table_section:
        sections.append(table_section)
    sections.append({"heading": "Attributs", "level": 1, "label": "attributes", "blocks": []})
    sections.extend(attr_sections)

    doc = {"lang": "fr", "title": title, "series": series, "source_url": source_url,
           "id_classe": id_classe, "sections": sections}
    return doc, ctx


def run(src_dir: Path, build_dir: Path, root: Path) -> Path:
    src_html = src_dir / "src.html"
    if not src_html.is_file():
        cands = list(src_dir.glob("*.html"))
        if len(cands) != 1:
            raise SystemExit(f"{src_dir}: expected src.html (or exactly one .html file)")
        src_html = cands[0]
    out_dir = build_dir
    if (out_dir / "img").exists():
        shutil.rmtree(out_dir / "img")
    out_dir.mkdir(parents=True, exist_ok=True)
    doc, ctx = parse(src_html, out_dir, root)
    out = out_dir / "doc.fr.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    n_attr = sum(1 for s in doc["sections"] if s["level"] == 2)
    n_val = sum(1 for s in doc["sections"] if s["level"] == 3)
    print(f"[parse] {out}: {n_attr} attributes, {n_val} values, {ctx.figures} figures, {ctx.tables} tables")
    for m in ctx.missing:
        print(f"[parse] WARNING: image not found in source dir: {m}", file=sys.stderr)
    return out
