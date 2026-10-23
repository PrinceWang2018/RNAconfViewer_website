"""Collect website and download statistics into stats.json (run daily by .github/workflows/update-stats.yml).

Sources
  downloads  GitHub release assets (download_count) of the repositories in STATS_REPOS
  visits     GoatCounter (GOATCOUNTER_CODE + GOATCOUNTER_TOKEN, a read-only API token)

Environment
  STATS_REPOS        comma-separated owner/name list (default: the RCV source and website repositories)
  GITHUB_TOKEN       optional, raises the GitHub API rate limit
  GOATCOUNTER_CODE   site code, e.g. "rcv" for https://rcv.goatcounter.com
  GOATCOUNTER_TOKEN  GoatCounter API token with "read statistics" permission
  STATS_SINCE        first day to count visits from (default 2026-10-24)

Only aggregate numbers are stored; GoatCounter does not record personal data.
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
SINCE = os.environ.get('STATS_SINCE', '2026-10-24')


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
                          for a in rel.get('assets', [])]
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


def visits(today):
    code, token = os.environ.get('GOATCOUNTER_CODE'), os.environ.get('GOATCOUNTER_TOKEN')
    if not (code and token):
        return None, ['GoatCounter not configured']
    base = f'https://{code}.goatcounter.com/api/v0'
    rng = f'start={SINCE}T00:00:00Z&end={(today + dt.timedelta(days=1)).isoformat()}T00:00:00Z'
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
            'countries': sorted(countries, key=lambda c: -c['count']), 'country_count': len(known)}, []


def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    old = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    dl, errors = downloads()
    try:
        vis, verr = visits(today)
    except (urllib.error.URLError, KeyError, ValueError) as e:
        vis, verr = old.get('visits'), [f'GoatCounter: {e}']    # keep the last good numbers
    errors += verr
    history = [h for h in old.get('download_history', []) if h['date'] != today.isoformat()]
    history.append({'date': today.isoformat(), 'total': dl['total']})
    stats = {'updated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
             'visits': vis, 'downloads': dl, 'download_history': history[-730:]}
    OUT.write_text(json.dumps(stats, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    for e in errors:
        print('note:', e, file=sys.stderr)
    print(f"downloads {dl['total']} · visits {vis['total'] if vis else '-'} -> {OUT.name}")


if __name__ == '__main__':
    main()
