"""Collect website and download statistics into stats.json (run daily by .github/workflows/update-stats.yml).

Sources
  downloads  GitHub release assets (download_count) of the repositories in STATS_REPOS
  visits     GoatCounter (GOATCOUNTER_CODE + GOATCOUNTER_TOKEN, a read-only API token)

Environment
  STATS_REPOS        comma-separated owner/name list (default: the RCV source and website repositories)
  GITHUB_TOKEN       optional, raises the GitHub API rate limit
  GOATCOUNTER_CODE   site code (default "princewang2018" -> https://princewang2018.goatcounter.com)
  GOATCOUNTER_TOKEN  GoatCounter API token with "read statistics" permission; needed for countries and months.
                     Without it only the total number of visits is collected (GoatCounter's public counter).
  STATS_SINCE        first day to count visits from (default 2026-10-23, when counting started)

Only aggregate numbers are stored; GoatCounter does not record personal data. Problems are printed as GitHub
Actions warnings, so they show up on the workflow run page.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'stats.json'
REPOS = [r.strip() for r in os.environ.get(
    'STATS_REPOS', 'PrinceWang2018/RNAconformer,PrinceWang2018/RNAconfViewer_website').split(',') if r.strip()]
SINCE = os.environ.get('STATS_SINCE') or '2026-10-23'
GC_CODE = os.environ.get('GOATCOUNTER_CODE') or 'princewang2018'


def warn(msg):
    """A note in the log; in GitHub Actions also a warning on the run page."""
    msg = ' '.join(str(msg).split())                         # one line (a workflow command ends at the newline)
    print(f'::warning::{msg}' if os.environ.get('GITHUB_ACTIONS') else f'note: {msg}', file=sys.stderr)


def get_json(url, token=None):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'rcv-website-stats'})
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def platform_of(name):
    n = name.lower()
    if n.endswith(('.exe', '.msi')) or 'windows' in n:
        return 'Windows'
    if n.endswith(('.dmg', '.pkg')) or 'macos' in n:
        return 'macOS (Apple Silicon)' if re.search(r'arm64|aarch64', n) else 'macOS (Intel)'
    if n.endswith(('.appimage', '.deb', '.rpm')) or 'linux' in n:
        return 'Linux'
    if n.endswith(('.whl', '.tar.gz', '.zip')):
        return 'Source / Python'
    return 'Other'


def is_checksum(name):
    """Checksum and signature files (SHA256SUMS.txt, *.sha256, *.asc, *.sig) are not downloads of RCV."""
    n = name.lower()
    return n.startswith('sha256sums') or n.endswith(('.sha256', '.asc', '.sig', '.txt'))


def downloads():
    token = os.environ.get('GITHUB_TOKEN')
    releases, by_platform, errors = [], defaultdict(int), []
    for repo in REPOS:
        page = 1
        while True:
            try:
                batch = get_json(f'https://api.github.com/repos/{repo}/releases?per_page=100&page={page}', token)
            except urllib.error.HTTPError as e:
                errors.append(f'{repo}: HTTP {e.code}')
                break
            for rel in batch:
                if rel.get('draft'):
                    continue
                assets = [{'name': a['name'], 'platform': platform_of(a['name']), 'count': a['download_count']}
                          for a in rel.get('assets', []) if not is_checksum(a['name'])]
                for a in assets:
                    by_platform[a['platform']] += a['count']
                releases.append({'tag': rel['tag_name'], 'name': rel.get('name') or rel['tag_name'],
                                 'date': (rel.get('published_at') or '')[:10], 'repo': repo,
                                 'total': sum(a['count'] for a in assets), 'assets': assets})
            if len(batch) < 100:
                break
            page += 1
    releases.sort(key=lambda r: r['date'], reverse=True)
    return {'total': sum(by_platform.values()), 'by_platform': dict(sorted(by_platform.items())),
            'releases': releases}, errors


def counter_total():
    """Total visits from GoatCounter's public counter (no token needed; 'Allow adding visitor counts' is on)."""
    d = get_json(f'https://{GC_CODE}.goatcounter.com/counter/TOTAL.json')
    return int(re.sub(r'\D', '', str(d.get('count', ''))) or 0)


def visits(now):
    """Visits since SINCE: total, per month and per country (API token), or only the total (public counter)."""
    token = os.environ.get('GOATCOUNTER_TOKEN')
    if not token:
        warn('GOATCOUNTER_TOKEN is not set: only the total number of visits is collected (no countries or months). '
             'Add the secret in Settings > Secrets and variables > Actions.')
        return {'total': counter_total(), 'since': SINCE, 'monthly': [], 'countries': [], 'country_count': None,
                'source': 'counter'}, []
    base = f'https://{GC_CODE}.goatcounter.com/api/v0'
    start = dt.datetime.fromisoformat(SINCE).replace(tzinfo=dt.timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)     # the API wants whole hours
    if start >= end:
        start = end - dt.timedelta(days=1)
    fmt = '%Y-%m-%dT%H:%M:%SZ'
    rng = f'start={start.strftime(fmt)}&end={end.strftime(fmt)}'
    total = get_json(f'{base}/stats/total?{rng}', token)
    months = defaultdict(int)
    for day in total.get('stats') or []:
        months[day['day'][:7]] += day.get('daily') or 0
    countries, offset = [], 0
    while True:
        loc = get_json(f'{base}/stats/locations?{rng}&limit=100&offset={offset}', token)
        countries += [{'name': s['name'] or 'Unknown', 'count': s['count']} for s in loc.get('stats') or []]
        if not loc.get('more'):
            break
        offset += 100
    known = [c for c in countries if c['name'] != 'Unknown']
    return {'total': total.get('total', 0), 'since': SINCE,
            'monthly': [{'month': m, 'count': months[m]} for m in sorted(months)],
            'countries': sorted(countries, key=lambda c: -c['count']), 'country_count': len(known),
            'source': 'api'}, []


def http_error(e):
    body = ''
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = re.sub(r'<(style|script)\b.*?</\1>|<[^>]+>', ' ', e.read().decode('utf-8', 'replace'), flags=re.S)
            body = ' '.join(body.split())[:200]
        except Exception:
            pass
    return f'{e} {body}'.strip()


def main():
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    old = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    dl, errors = downloads()
    try:
        vis, verr = visits(now)
    except (urllib.error.URLError, KeyError, ValueError) as e:
        verr = [f'GoatCounter API: {http_error(e)}']
        try:                                                       # at least the total, from the public counter
            vis = {'total': counter_total(), 'since': SINCE, 'monthly': [], 'countries': [], 'country_count': None,
                   'source': 'counter'}
            if old.get('visits') and old['visits'].get('source') == 'api':
                vis = {**old['visits'], 'total': max(old['visits']['total'], vis['total'])}   # keep the last details
        except (urllib.error.URLError, ValueError) as e2:
            vis = old.get('visits')
            verr.append(f'GoatCounter counter: {http_error(e2)}')
    errors += verr
    history = [h for h in old.get('download_history', []) if h['date'] != today.isoformat()]
    history.append({'date': today.isoformat(), 'total': dl['total']})
    stats = {'updated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
             'visits': vis, 'downloads': dl, 'download_history': history[-730:]}
    OUT.write_text(json.dumps(stats, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    for e in errors:
        warn(e)
    print(f"downloads {dl['total']} · visits {vis['total'] if vis else '-'} -> {OUT.name}")


if __name__ == '__main__':
    main()
