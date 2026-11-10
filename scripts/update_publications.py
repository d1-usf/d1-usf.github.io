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
CANDIDATES = [
    f"{BASE}/{PERSON_ID}/JSON/{PERSON_ID}.js",
    f"{BASE}/Diouane=3AYoussef=3A=3A/JSON/Diouane=3AYoussef=3A=3A.js",
]
ME_FAMILY = "Diouane"

TYPE_MAP = {                       # EPrints type -> homepage type
    "article": "j",
    "conference_item": "c",
    "book_section": "c",
    "monograph": "r",              # technical reports (Cahiers du GERAD, ...)
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "homepage-publication-sync/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


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
    data, last_err = None, None
    for url in CANDIDATES:
        try:
            data = fetch(url)
            print(f"Fetched {url}")
            break
        except Exception as e:                           # try next candidate
            last_err = e
            print(f"Could not fetch {url}: {e}", file=sys.stderr)
    if data is None:
        print("No export could be read; publications.json left unchanged.", file=sys.stderr)
        sys.exit(1 if last_err else 0)

    rows = convert(data if isinstance(data, list) else data.get("items", []))
    if EXTRA.exists():
        rows += json.loads(EXTRA.read_text(encoding="utf-8"))
    rows = dedupe(rows)
    if len(rows) < 10:                                   # safety net against an empty or broken export
        print(f"Only {len(rows)} publications parsed; refusing to overwrite.", file=sys.stderr)
        sys.exit(1)

    old = json.loads(OUT.read_text(encoding="utf-8")).get("publications") if OUT.exists() else None
    if old == rows:
        print("No change.")
        return
    OUT.write_text(json.dumps({"source": "PolyPublie, Polytechnique Montréal", "updated": datetime.date.today().isoformat(),
                               "publications": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(rows)} publications to {OUT.name}")


if __name__ == "__main__":
    main()
