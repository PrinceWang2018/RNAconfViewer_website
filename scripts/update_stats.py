"""Collect website and download statistics into stats.json (run daily by .github/workflows/update-stats.yml).

Sources
  downloads  GitHub release assets (download_count) of the repositories in STATS_REPOS; releases without
             installer files (e.g. the source-code release that Zenodo archives) are left out
  zenodo     downloads of the source code from the Zenodo record of the citation DOI, all versions (public
             statistics, COUNTER rules: robots and double clicks are not counted); a row "Source code (Zenodo)"
  visits     Cloudflare's analytics of the www.rnaconfviewer.com zone (GraphQL Analytics API, daily totals);
             every day is also kept in data/visits_daily.json, so the totals go back to the first day on record

Environment
  STATS_REPOS        comma-separated owner/name list (default: the RCV source and website repositories)
  GITHUB_TOKEN       optional, raises the GitHub API rate limit
  CLOUDFLARE_API_TOKEN  API token with the permission Zone > Analytics > Read for the zone (secret)
  CLOUDFLARE_ZONE_ID    the zone's ID (Cloudflare dashboard > the domain > Overview > API > Zone ID)
  ZENODO_CONCEPT        Zenodo concept record of RCV (default 24163503; its latest version has the statistics)
  CLOUDFLARE_SINCE      first day to ask Cloudflare for (default 2026-10-01)

Only aggregate numbers are stored (per day and country); no addresses or other personal data. Problems are printed as GitHub
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
DAILY = Path(__file__).resolve().parent.parent / 'data' / 'visits_daily.json'
ZENODO_CONCEPT = os.environ.get('ZENODO_CONCEPT') or '24163503'
ZENODO_ROW = 'Source code (Zenodo)'
CF_FIRST = os.environ.get('CLOUDFLARE_SINCE') or '2026-10-01'
NOT_COUNTRIES = {'XX', 'T1'}              # Cloudflare: unknown country, Tor network


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
                if not assets:
                    # A release without installer files is not a download: the GitHub release of the source
                    # repository that Zenodo archives for the DOI (named "RNA Conformation Viewer") has none.
                    continue
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


def zenodo_downloads():
    """Downloads of all versions of the Zenodo record (the API redirects to the latest version)."""
    d = get_json(f'https://zenodo.org/api/records/{ZENODO_CONCEPT}/versions/latest')
    return int(d['stats']['downloads'])


def cf_graphql(query, variables, token):
    req = urllib.request.Request('https://api.cloudflare.com/client/v4/graphql',
                                 data=json.dumps({'query': query, 'variables': variables}).encode(),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'rcv-website-stats',
                                          'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    if d.get('errors'):
        raise ValueError('; '.join(e.get('message', str(e)) for e in d['errors']))
    return d['data']


CF_SETTINGS = """query ($zone: String!) { viewer { zones(filter: {zoneTag: $zone}) {
  settings { httpRequests1dGroups { maxDuration notOlderThan } } } } }"""
CF_DAYS = """query ($zone: String!, $from: Date!, $to: Date!) { viewer { zones(filter: {zoneTag: $zone}) {
  httpRequests1dGroups(limit: 1000, orderBy: [date_ASC], filter: {date_geq: $from, date_leq: $to}) {
    dimensions { date }
    sum { requests pageViews countryMap { clientCountryName requests } }
    uniq { uniques } } } } }"""


def cloudflare_days(today):
    """The days Cloudflare still keeps: {date: {uniques, requests, page_views, countries: {code: requests}}}."""
    token, zone = os.environ.get('CLOUDFLARE_API_TOKEN'), os.environ.get('CLOUDFLARE_ZONE_ID')
    if not token or not zone:
        raise ValueError('CLOUDFLARE_API_TOKEN (secret) or CLOUDFLARE_ZONE_ID (variable) is not set')
    oldest, step = 364, 31                                   # days; replaced by the zone's own limits below
    try:
        st = cf_graphql(CF_SETTINGS, {'zone': zone}, token)['viewer']['zones'][0]['settings']['httpRequests1dGroups']
        oldest = int(st['notOlderThan']) // 86400 - 1
        step = max(1, int(st['maxDuration']) // 86400 - 1)
    except (urllib.error.URLError, KeyError, IndexError, TypeError, ValueError) as e:
        warn(f'Cloudflare query limits not available ({http_error(e)}); asking for the last {oldest + 1} days')
    days, start = {}, max(today - dt.timedelta(days=oldest), dt.date.fromisoformat(CF_FIRST))
    while start <= today:
        end = min(start + dt.timedelta(days=step), today)
        zones = cf_graphql(CF_DAYS, {'zone': zone, 'from': start.isoformat(), 'to': end.isoformat()},
                           token)['viewer']['zones']
        for g in (zones[0]['httpRequests1dGroups'] if zones else []):
            s = g['sum']
            days[g['dimensions']['date']] = {
                'uniques': g['uniq']['uniques'], 'requests': s['requests'], 'page_views': s['pageViews'],
                'countries': {c['clientCountryName']: c['requests'] for c in s['countryMap'] if c['requests']}}
        start = end + dt.timedelta(days=1)
    return days


def visits(today):
    """Visitors from Cloudflare, from the first day on record.

    Cloudflare keeps daily totals for a limited time (a year on the Free plan), so every day is also kept in
    data/visits_daily.json and the totals are summed from that file. Visitors are Cloudflare's unique visitors
    (distinct network addresses) per day, summed over the days. Cloudflare counts requests, not visitors, per
    country, so a country's visitors are estimated by sharing each day's visitors out by the requests."""
    archive = json.loads(DAILY.read_text(encoding='utf-8')) if DAILY.exists() else {}
    archive.update(cloudflare_days(today))
    archive = {d: archive[d] for d in sorted(archive)}
    DAILY.parent.mkdir(exist_ok=True)
    DAILY.write_text('{\n' + ',\n'.join(f'{json.dumps(d)}: {json.dumps(v, separators=(",", ":"))}'
                                         for d, v in archive.items()) + '\n}\n', encoding='utf-8')   # a line a day
    counted = [d for d in archive if archive[d]['requests']]
    months, est, req = defaultdict(int), defaultdict(float), defaultdict(int)
    for d in counted:
        day = archive[d]
        months[d[:7]] += day['uniques']
        total_req = sum(day['countries'].values()) or 1
        for c, n in day['countries'].items():
            est[c] += day['uniques'] * n / total_req
            req[c] += n
    countries = sorted(({'code': c, 'count': round(est[c]), 'requests': req[c]} for c in est),
                       key=lambda c: (-c['count'], -c['requests']))
    real = [c for c in countries if c['code'] not in NOT_COUNTRIES]
    return {'total': sum(archive[d]['uniques'] for d in counted), 'since': counted[0] if counted else None,
            'requests': sum(archive[d]['requests'] for d in counted),
            'page_views': sum(archive[d]['page_views'] for d in counted),
            'monthly': [{'month': m, 'count': months[m]} for m in sorted(months)],
            'countries': countries, 'country_count': len(real), 'source': 'cloudflare'}


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
    sources = {'github': dl['total']}
    try:
        zen = zenodo_downloads()
    except (urllib.error.URLError, KeyError, TypeError, ValueError) as e:
        zen = (old.get('downloads') or {}).get('sources', {}).get('zenodo')        # keep the last number
        errors.append(f'Zenodo: {http_error(e)}')
    if zen is not None:
        sources['zenodo'] = zen
        dl['by_platform'][ZENODO_ROW] = zen
    dl['sources'] = sources
    dl['total'] = sum(sources.values())
    verr = []
    try:
        vis = visits(today)
    except (urllib.error.URLError, KeyError, IndexError, TypeError, ValueError) as e:
        vis = old.get('visits')                                     # keep the last numbers
        verr.append(f'Cloudflare analytics: {http_error(e)}')
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
