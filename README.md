# RCV website

Website of [RCV — RNA Conformation Viewer](https://github.com/PrinceWang2018/RNAconformer).
A single static page (`index.html`, `images/`), served with GitHub Pages.

## Publish

Settings ▸ Pages ▸ *Deploy from a branch* ▸ `master` / `(root)`.

## Statistics

The *Statistics* tab and the footer read `stats.json`, which
`.github/workflows/update-stats.yml` refreshes once a day with `scripts/update_stats.py`:

* **Downloads** — `download_count` of the release assets of `PrinceWang2018/RNAconformer` and of this
  repository (GitHub API; nothing to configure). Attach the installers to a GitHub release to have them counted.
* **Visits, countries, visits per month** — [GoatCounter](https://www.goatcounter.com) (free for
  non-commercial use, no cookies, no personal data). To enable it:
  1. Create a site at goatcounter.com and choose a code, e.g. `rcv` → `https://rcv.goatcounter.com`.
  2. In `index.html`, set `var GOATCOUNTER_CODE = 'rcv';` (near the end of the file).
  3. In GoatCounter, *Settings ▸ API* — create a token with *Read statistics* permission.
  4. In this repository, *Settings ▸ Secrets and variables ▸ Actions*: add the secret `GOATCOUNTER_TOKEN`
     and the variable `GOATCOUNTER_CODE`.
  5. *Actions ▸ Update statistics ▸ Run workflow* once to check.

Until GoatCounter is set up, the visit numbers stay hidden and only downloads are shown.

Run locally: `python scripts/update_stats.py` (with the same environment variables), then
`python -m http.server` and open http://localhost:8000.
