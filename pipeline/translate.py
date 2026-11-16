"""Translate doc.fr.json -> doc.en.json with DeepL (glossary + persistent translation cache).

Only cache misses are sent to DeepL, so re-running a document costs 0 characters.
The API key is read from the DEEPL_AUTH_KEY environment variable and never stored.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

TARGET_LANG = "EN-GB"
BATCH_TEXTS = 50          # DeepL max texts per request
BATCH_CHARS = 30_000      # stay well under the 128 KiB request limit


# --------------------------------------------------------------------------- walking


def map_strings(doc: dict, fn: Callable[[str], str]) -> dict:
    """Return a copy of doc with every translatable string passed through fn."""
    doc = copy.deepcopy(doc)
    doc["title_fr"] = doc["title"]
    doc["title"] = fn(doc["title"])
    doc["series"] = fn(doc["series"])

    def block(b: dict):
        t = b["type"]
        if t == "para":
            b["html"] = fn(b["html"])
        elif t == "list":
            b["items"] = [fn(i) for i in b["items"]]
        elif t == "meta":
            for it in b["items"]:
                it["label"] = fn(it["label"])
                it["html"] = fn(it["html"])
        elif t == "article":
            b["label"] = fn(b["label"])
            for c in b["blocks"]:
                block(c)
        elif t == "table":
            b["header"] = [fn(h) for h in b["header"]]
            b["rows"] = [[fn(c) for c in row] for row in b["rows"]]
            b["caption"] = fn(b.get("caption", ""))
        elif t == "figure":
            b["caption"] = fn(b.get("caption", ""))

    for s in doc["sections"]:
        s["heading"] = fn(s["heading"])
        for b in s["blocks"]:
            block(b)
    doc["lang"] = "en"
    return doc


def needs_translation(s: str) -> bool:
    """Skip empty strings, pure identifiers (<code>…</code>) and numbers/punctuation."""
    if not s or not s.strip():
        return False
    visible = re.sub(r"<code>.*?</code>", "", s)
    visible = re.sub(r"<[^>]+>", "", visible)
    return bool(re.search(r"[A-Za-zÀ-ÿ]{2,}", visible))


# --------------------------------------------------------------------------- glossary + cache


def load_glossary(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    entries: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2 or not row[0].strip() or row[0].lstrip().startswith("#") or row[0] == "fr":
                continue
            entries[row[0].strip()] = row[1].strip()
    return entries


def glossary_hash(entries: dict[str, str]) -> str:
    blob = json.dumps(sorted(entries.items()), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


class Cache:
    def __init__(self, path: Path, salt: str):
        self.path, self.salt = path, salt
        self.data: dict[str, str] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.data[rec["k"]] = rec["en"]

    def key(self, fr: str) -> str:
        return hashlib.sha256(f"{self.salt}\n{TARGET_LANG}\n{fr}".encode()).hexdigest()

    def get(self, fr: str) -> str | None:
        return self.data.get(self.key(fr))

    def put_many(self, pairs: list[tuple[str, str]]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for fr, en in pairs:
                k = self.key(fr)
                self.data[k] = en
                f.write(json.dumps({"k": k, "fr": fr, "en": en}, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- DeepL


def _client():
    key = os.environ.get("DEEPL_AUTH_KEY")
    if not key:
        raise SystemExit("DEEPL_AUTH_KEY is not set (export it in your shell; never commit it).")
    import deepl
    return deepl.DeepLClient(key)


def _ensure_glossary(client, entries: dict[str, str], ghash: str):
    if not entries:
        return None
    name = f"fr2en-{ghash}"
    for g in client.list_glossaries():
        if g.name == name and g.ready:
            return g
    print(f"[translate] creating DeepL glossary {name} ({len(entries)} entries)")
    return client.create_glossary(name, source_lang="FR", target_lang="EN", entries=entries)


def _batches(texts: list[str]):
    batch, size = [], 0
    for t in texts:
        if batch and (len(batch) >= BATCH_TEXTS or size + len(t) > BATCH_CHARS):
            yield batch
            batch, size = [], 0
        batch.append(t)
        size += len(t)
    if batch:
        yield batch


def run(fr_json: Path, en_json: Path, root: Path, dry_run: bool = False) -> Path | None:
    doc = json.loads(fr_json.read_text(encoding="utf-8"))
    entries = load_glossary(root / "glossary.csv")
    ghash = glossary_hash(entries)
    cache = Cache(root / "cache" / "translations.jsonl", ghash)

    wanted: list[str] = []
    map_strings(doc, lambda s: (wanted.append(s) if needs_translation(s) else None) or s)
    unique = list(dict.fromkeys(wanted))
    misses = [s for s in unique if cache.get(s) is None]
    chars = sum(len(s) for s in misses)
    print(f"[translate] {len(unique)} unique strings, {len(unique) - len(misses)} cached, "
          f"{len(misses)} to send ({chars:,} chars), glossary {ghash} ({len(entries)} entries)")

    if dry_run:
        if os.environ.get("DEEPL_AUTH_KEY"):
            u = _client().get_usage()
            if u.character.valid:
                left = u.character.limit - u.character.count
                print(f"[translate] DeepL quota: {u.character.count:,}/{u.character.limit:,} used, {left:,} left"
                      + ("  ⚠ NOT ENOUGH" if chars > left else ""))
        return None

    if misses:
        client = _client()
        glossary = _ensure_glossary(client, entries, ghash)
        done = 0
        for batch in _batches(misses):
            results = client.translate_text(
                batch, source_lang="FR", target_lang=TARGET_LANG,
                tag_handling="html", ignore_tags=["code"], glossary=glossary,
            )
            cache.put_many([(fr, r.text) for fr, r in zip(batch, results)])
            done += len(batch)
            print(f"[translate] {done}/{len(misses)}", end="\r", file=sys.stderr)
        print(file=sys.stderr)
        u = client.get_usage()
        if u.character.valid:
            print(f"[translate] DeepL quota now {u.character.count:,}/{u.character.limit:,}")

    en = map_strings(doc, lambda s: (cache.get(s) or s) if needs_translation(s) else s)
    en_json.write_text(json.dumps(en, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[translate] {en_json}")
    return en_json
