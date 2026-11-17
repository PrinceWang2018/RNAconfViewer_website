# RCV website

Website of [RCV — RNA Conformation Viewer](https://github.com/PrinceWang2018/RNAconformer).
A static site (`index.html`, `images/`, the user guide in `guide/`), published at **https://www.rnaconfviewer.com/**.

## Publish

The site is served by Cloudflare (a Worker with static assets, `wrangler.jsonc`) from the `master` branch of
this repository: every push (including the daily statistics commit) is deployed automatically. No build step; the output directory is the
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
once a day with `scripts/update_stats.py`, so every number on it, including the total of visits, changes once a day.

* **Downloads** — `download_count` of the release files of `PrinceWang2018/RNAconformer` and of this
  repository (GitHub API; nothing to configure). Releases without installer files are left out: the
  RNAconformer releases that Zenodo archives for the citation DOI carry only the source code.
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

## Feedback

The site is a Cloudflare **Worker with static assets** (`wrangler.jsonc`): every file is served as a static
asset, as before, and only two addresses run the script in `worker/` (`run_worker_first`):

* `POST /api/feedback` (`worker/feedback.js`) stores a comment from the *Feedback* tab in a Cloudflare D1
  database (free plan);
* **https://www.rnaconfviewer.com/admin/feedback** (`worker/admin.js`) shows them: mark read, delete, reply by
  email, download all as CSV. User `admin`, password = the secret below. They can also be browsed in the
  Cloudflare dashboard: *Storage & Databases ▸ D1 ▸ rcv-feedback ▸ Explore data ▸ feedback*.

`.assetsignore` keeps the script, the configuration, `scripts/` and the README out of the public files.

One-time setup:

1. Cloudflare dashboard ▸ *Storage & Databases ▸ D1 ▸ Create database*, name `rcv-feedback`. Copy its
   *Database ID* into `wrangler.jsonc` (`database_id`). The table is created with the first comment.
2. `wrangler.jsonc` ▸ `name`: the name of the existing Worker of this site (*Workers & Pages* overview), so the
   deploy updates it instead of creating a second Worker.
3. The Worker ▸ *Settings ▸ Variables and Secrets ▸ Add*: type **Secret**, name `FEEDBACK_ADMIN_PASSWORD`, a
   long password. Optionally a second secret `FEEDBACK_SALT` (any random text) for the hashed addresses of the
   rate limit. Secrets are kept across deploys.
4. The Worker ▸ *Settings ▸ Build*: the deploy command should be `npx wrangler deploy` (it reads
   `wrangler.jsonc`). Push; the build deploys the script, the binding and the files together.

The D1 binding is defined in `wrangler.jsonc`, not in the dashboard: a deploy replaces bindings made by hand.
Until the setup is done the form says that feedback is not available and points to email. Spam protection:
a hidden field that bots fill in, and at most 5 comments an hour from one address (only a salted hash of the
address is stored).

Test locally: `npx wrangler dev` (local D1), then http://localhost:8787/#feedback and /admin/feedback with
`FEEDBACK_ADMIN_PASSWORD=test` in a `.dev.vars` file.
