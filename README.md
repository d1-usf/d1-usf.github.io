# Prof. Youssef Diouane — homepage

Static site: `index.html` plus `publications.json`, which a GitHub Action refreshes every day from PolyPublie (Polytechnique Montréal).

## Put it online (GitHub Pages)
1. Create a repository named `<username>.github.io` (or any repository with Pages turned on).
2. Upload everything in this folder, including the hidden `.github` folder.
3. Settings → Pages → Source: "Deploy from a branch", branch `main`, folder `/ (root)`.
4. Actions tab → "Update publications from PolyPublie" → **Run workflow** once to check that it works.
   After that it runs by itself every day at 09:17 UTC and commits `publications.json` only when something changed.

## How the publication list works
- `scripts/update_publications.py` downloads the JSON export of your PolyPublie person page
  (https://publications.polymtl.ca/view/person/Diouane,_Youssef.html), keeps the journal articles,
  conference papers and technical reports you authored, drops a report when the same title exists as a
  paper, and writes `publications.json`.
- `index.html` loads `publications.json` when the page opens. If the file is missing or unreadable,
  the page shows the list built into the HTML, so it never appears empty.
- To run the sync by hand: `python scripts/update_publications.py` (Python 3, no extra packages).

Other hosts (Polytechnique web space, etc.): upload `index.html` and `publications.json` and run the script on any machine
with a daily scheduled task (cron), then upload the new `publications.json`.
