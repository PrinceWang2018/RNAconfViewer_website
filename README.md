# RCV website

Website of [RCV — RNA Conformation Viewer](https://github.com/PrinceWang2018/RNAconformer).
A static site (`index.html`, `images/`, the user guide in `guide/`), published at **https://www.rnaconfviewer.com/**.

## Publish

The site is served by Cloudflare Pages from the `master` branch of this repository: every push (including
the daily statistics commit) is deployed automatically. No build step; the output directory is the
repository root.

`guide/` is the RCV user guide, plugin guide and changelog as web pages. Regenerate it from the RCV source
folder when the documentation changes:

```bash
python ../RNAconformer/packaging/make_docs.py guide --site
```

## Downloads

Cloudflare Pages serves at most **25 MiB per file**; the RCV installers are larger (Windows ≈ 41 MiB), so they
are **not** part of the site (`downloads/` is the local copy and is ignored by git). They are files of a
**GitHub release of this repository**, and `_redirects` gives them website addresses:

```
https://www.rnaconfviewer.com/download/v0.6.0/RCV-0.6.0-Windows-x64-Setup.exe
  → https://github.com/PrinceWang2018/RNAconfViewer_website/releases/download/v0.6.0/RCV-0.6.0-Windows-x64-Setup.exe
```

To publish a version:

1. On GitHub, open this repository ▸ *Releases* ▸ *Draft a new release*. Tag: `v0.6.0` (create it on
   `master`), title `RCV 0.6.0`.
2. Drag the installers into the release: `RCV-0.6.0-Windows-x64-Setup.exe`, `RCV-0.6.0-macOS-arm64.dmg`,
   `RCV-0.6.0-macOS-x86_64.dmg`, `RCV-0.6.0-Linux-amd64.deb` and `RCV-0.6.0-Linux-x86_64.rpm` (the *Build
   installers* workflow of the RNAconformer repository builds all of them; it can also attach them itself: see
   `packaging/README.md` there). Add `SHA256SUMS.txt` too (`sha256sum RCV-* > SHA256SUMS.txt`). *Publish release*.
3. In `index.html`, the Download tab links to `https://www.rnaconfviewer.com/download/v<version>/<file>`;
   change the version there for the next release. The links work as soon as the release is published.

Downloads are counted by GitHub and appear in the Statistics tab.

## Statistics

The *Statistics* tab and the footer read `stats.json`, which `.github/workflows/update-stats.yml` refreshes
once a day with `scripts/update_stats.py`; the page also asks GoatCounter for the current total of visits.

* **Downloads** — `download_count` of the release files of `PrinceWang2018/RNAconformer` and of this
  repository (GitHub API; nothing to configure).
* **Visits** — [GoatCounter](https://www.goatcounter.com) (free for non-commercial use, no cookies, no personal
  data), site `princewang2018` → https://princewang2018.goatcounter.com. The total of visits works without any
  setup (GoatCounter's public counter). **Countries and visits per month** need a read-only API token:
  1. In GoatCounter: *Settings ▸ API ▸ New API key*, with the permission *Read statistics*. Copy the key.
  2. In this repository on GitHub: *Settings ▸ Secrets and variables ▸ Actions ▸ New repository secret*,
     name `GOATCOUNTER_TOKEN`, value: the key.
  3. *Actions ▸ Update statistics ▸ Run workflow*. Problems are shown as warnings on the run's page.

  (A different GoatCounter site can be set with the repository variable `GOATCOUNTER_CODE`.)

Run locally: `python scripts/update_stats.py` (with the same environment variables), then
`python -m http.server` and open http://localhost:8000.
