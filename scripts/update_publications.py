#!/usr/bin/env python3
"""Sync publications.json with Youssef Diouane's PolyPublie profile (Polytechnique Montréal).

PolyPublie is an EPrints repository. Its "person" view can be exported as JSON:
    https://publications.polymtl.ca/view/person/Diouane,_Youssef.html
This script downloads that export, keeps the items you authored (journal articles,
conference papers, technical reports), converts them to the format the homepage reads,
merges optional manual entries from publications-extra.json, and writes publications.json.

Standard library only. Run:  python scripts/update_publications.py
"""
import json, re, sys, unicodedata, urllib.request, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "publications.json"
EXTRA = ROOT / "publications-extra.json"

PERSON_ID = "ab48fd4d691fbba8bac37dd95723f7ef"   # id of the PolyPublie person view
BASE = "https://publications.polymtl.ca/cgi/exportview/person"
CANDIDATES = [                                   # (format, url) tried in order
    ("bibtex", f"{BASE}/{PERSON_ID}/BibTeX/{PERSON_ID}.bib"),
    ("json",   f"{BASE}/{PERSON_ID}/JSON/{PERSON_ID}.js"),
]
ME_FAMILY = "Diouane"

TYPE_MAP = {                       # EPrints type -> homepage type
    "article": "j",
    "conference_item": "c",
    "book_section": "c",
    "monograph": "r",              # technical reports (Cahiers du GERAD, ...)
}


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "homepage-publication-sync/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


# ---------- BibTeX ----------
ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "c": "\u0327", "=": "\u0304", ".": "\u0307", "v": "\u030c", "u": "\u0306", "H": "\u030b", "k": "\u0328"}


def delatex(t):
    t = re.sub(r"\\(['`^\"~=.])\s*\{?\\?([A-Za-z])\}?", lambda m: unicodedata.normalize("NFC", m.group(2) + ACCENTS[m.group(1)]), t)
    t = re.sub(r"\\([cvuHk])\s*\{([A-Za-z])\}", lambda m: unicodedata.normalize("NFC", m.group(2) + ACCENTS[m.group(1)]), t)
    t = t.replace("\\&", "&").replace("--", "–").replace("\\%", "%").replace("\\_", "_")
    t = re.sub(r"\\[a-zA-Z]+\s*", "", t)          # drop remaining commands such as \textit
    return re.sub(r"\s+", " ", t.replace("{", "").replace("}", "")).strip()


def parse_bibtex(text):
    entries, i = [], 0
    while True:
        m = re.compile(r"@(\w+)\s*\{", re.S).search(text, i)
        if not m:
            break
        typ, j, depth = m.group(1).lower(), m.end(), 1
        k = j
        while k < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            k += 1
        body, i = text[j:k - 1], k
        fields, pos = {}, body.find(",") + 1
        while pos < len(body):
            fm = re.compile(r"\s*([\w-]+)\s*=\s*", re.S).match(body, pos)
            if not fm:
                break
            name, pos = fm.group(1).lower(), fm.end()
            if pos < len(body) and body[pos] == "{":
                d, q = 1, pos + 1
                while q < len(body) and d:
                    d += {"{": 1, "}": -1}.get(body[q], 0)
                    q += 1
                val, pos = body[pos + 1:q - 1], q
            elif pos < len(body) and body[pos] == '"':
                q = body.find('"', pos + 1)
                val, pos = body[pos + 1:q], q + 1
            else:
                q = re.compile(r"[,\n]").search(body, pos)
                q = q.start() if q else len(body)
                val, pos = body[pos:q], q
            fields[name] = delatex(val)
            nxt = body.find(",", pos)
            pos = nxt + 1 if nxt != -1 else len(body)
        entries.append((typ, fields))
    return entries


def bib_creators(s):
    out = []
    for a in re.split(r"\s+and\s+", s or ""):
        a = a.strip()
        if not a:
            continue
        if "," in a:
            fam, giv = [x.strip() for x in a.split(",", 1)]
        else:
            parts = a.split()
            fam, giv = parts[-1], " ".join(parts[:-1])
        out.append({"name": {"family": fam, "given": giv}})
    return out


BIB_TYPE = {"article": "article", "inproceedings": "conference_item", "conference": "conference_item",
            "incollection": "book_section", "techreport": "monograph"}


def bibtex_items(text):
    items = []
    for typ, f in parse_bibtex(text):
        t = BIB_TYPE.get(typ)
        if typ == "misc" and (f.get("booktitle") or f.get("eventtitle") or f.get("howpublished")):
            t = "conference_item"
        if not t:
            continue
        items.append({"type": t, "title": f.get("title", ""), "date": f.get("year", ""),
                      "creators": bib_creators(f.get("author")), "publication": f.get("journal"),
                      "volume": f.get("volume"), "number": f.get("number"), "pagerange": f.get("pages"),
                      "event_title": f.get("booktitle") or f.get("eventtitle") or f.get("howpublished"),
                      "event_location": f.get("address"), "series": f.get("institution") or f.get("series"),
                      "uri": f.get("url") or (f"https://doi.org/{f['doi']}" if f.get("doi") else "")})
    return items


def initials(given):
    parts = re.split(r"([\s-]+)", (given or "").strip())
    out = ""
    for p in parts:
        if not p:
            continue
        if p.strip() == "":
            out += " "
        elif p.strip() == "-":
            out += "-"
        else:
            out += p[0].upper() + "."
    return re.sub(r"\s+", " ", out).strip()


def author_list(creators):
    names = []
    for c in creators or []:
        n = c.get("name") or {}
        fam, giv = (n.get("family") or "").strip(), (n.get("given") or "").strip()
        if fam:
            names.append(f"{fam}, {initials(giv)}" if giv else fam)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + ", & " + names[-1]


def is_author(item):
    return any(((c.get("name") or {}).get("family") or "").lower() == ME_FAMILY.lower() for c in item.get("creators") or [])


def year_of(item):
    m = re.match(r"(\d{4})", str(item.get("date") or ""))
    return int(m.group(1)) if m else None


def venue(item, t):
    if t == "j":
        v = item.get("publication") or ""
        vol, num, pages = item.get("volume"), item.get("number"), item.get("pagerange") or item.get("article_number")
        if vol:
            v += f", {vol}" + (f"({num})" if num else "")
        if pages:
            v += f", {pages}"
        if item.get("ispublished") in ("inpress", "accepted"):
            v += " (accepted)"
        return v
    if t == "c":
        v = item.get("event_title") or item.get("book_title") or item.get("publication") or ""
        loc = item.get("event_location")
        return f"{v}, {loc}" if v and loc else v
    series, num = item.get("series") or item.get("institution") or item.get("publisher") or "", item.get("number") or item.get("id_number") or ""
    return f"{series} {num}".strip()


def norm(title):
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def convert(items):
    rows = []
    for it in items:
        t = TYPE_MAP.get(it.get("type"))
        title = it.get("title") or ""
        if isinstance(title, list):                     # some EPrints store multilang titles
            title = (title[0] or {}).get("text", "")
        title = title.strip()
        y = year_of(it)
        if not t or not title or not y or not is_author(it):
            continue
        rows.append({"type": t, "year": y, "title": title, "authors": author_list(it.get("creators")),
                     "venue": venue(it, t), "url": it.get("uri") or it.get("official_url") or ""})
    return rows


def dedupe(rows):
    """Keep one entry per title: journal > conference > report (a report later published is dropped)."""
    rank = {"j": 0, "c": 1, "r": 2}
    best = {}
    for r in rows:
        k = norm(r["title"])
        if k not in best or (rank[r["type"]], -r["year"]) < (rank[best[k]["type"]], -best[k]["year"]):
            best[k] = r
    return sorted(best.values(), key=lambda r: (-r["year"], rank[r["type"]], r["title"].lower()))


def main():
    items = None
    for fmt, url in CANDIDATES:
        try:
            text = fetch_text(url)
        except Exception as e:
            print(f"Could not fetch {url}: {e}", file=sys.stderr)
            continue
        try:
            if fmt == "bibtex":
                items = bibtex_items(text)
            else:
                data = json.loads(text)
                items = data if isinstance(data, list) else data.get("items", [])
        except Exception as e:
            items = None
            print(f"Could not read {fmt} from {url}: {e}", file=sys.stderr)
        if items:
            print(f"Read {len(items)} items ({fmt}) from {url}")
            break
        print(f"No usable items in {fmt} export. Start of response:\n{text[:400]}", file=sys.stderr)
        items = None
    if not items:
        print("No export could be read; publications.json left unchanged.", file=sys.stderr)
        sys.exit(1)

    rows = convert(items)
    if EXTRA.exists():
        rows += json.loads(EXTRA.read_text(encoding="utf-8"))
    rows = dedupe(rows)
    if len(rows) < 10:                                   # safety net against an empty or broken export
        print(f"Only {len(rows)} publications parsed; refusing to overwrite.", file=sys.stderr)
        sys.exit(1)

    old = json.loads(OUT.read_text(encoding="utf-8")).get("publications") if OUT.exists() else None
    # Always rewrite the file: "updated" is the date of the last successful check, so the
    # homepage shows "Synced from PolyPublie on <today>" even when no new paper appeared.
    # The resulting daily commit also keeps the repository active, so GitHub never pauses
    # the scheduled workflow (it does so after 60 days without activity in public repos).
    OUT.write_text(json.dumps({"source": "PolyPublie, Polytechnique Montréal", "updated": datetime.date.today().isoformat(),
                               "publications": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    if old == rows:
        print(f"No new publications ({len(rows)} listed); sync date refreshed.")
    else:
        print(f"Wrote {len(rows)} publications to {OUT.name}")


if __name__ == "__main__":
    main()
