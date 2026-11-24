"""Build images/world-map.json, the world map of the Statistics tab (run by hand; the output is committed).

    python scripts/make_world_map.py countries-110m.json countries-50m.json iso.csv

Inputs (download once, they are not kept in this repository)
  countries-110m.json, countries-50m.json
      https://cdn.jsdelivr.net/npm/world-atlas@2/  (Natural Earth 1:110m and 1:50m, public domain; package ISC)
  iso.csv
      https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv
      (columns alpha-2 and country-code: ISO 3166 numeric code -> two-letter code)

Output: {"w", "h", "shapes": {"US": "M…Z", …}, "dots": {"SG": [x, y], …}} in the Equal Earth projection.
Countries are keyed by their ISO 3166 two-letter code, the code Cloudflare reports (clientCountryName).
Countries too small for the 1:110m map (Singapore, Malta, Bahrain, …) are a dot at their 1:50m position.
Antarctica is left out.
"""
import csv
import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'images' / 'world-map.json'
WIDTH = 960
NO_ID = {'Kosovo': 'XK', 'N. Cyprus': 'CY', 'Somaliland': 'SO'}   # shapes without an ISO numeric code
SKIP = {'AQ'}

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def equal_earth(lon, lat):
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(M * math.sin(phi))
    t2 = t * t
    t6 = t2 * t2 * t2
    x = lam * math.cos(t) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


def decode(topo):
    """TopoJSON -> {geometry index: list of polygons, each a list of rings of (lon, lat)}."""
    (sx, sy), (tx, ty) = topo['transform']['scale'], topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        pts = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(a if not pts else a[1:])
        return pts

    out = []
    for g in topo['objects']['countries']['geometries']:
        polys = []
        if g.get('type') == 'Polygon':
            polys = [[ring(r) for r in g['arcs']]]
        elif g.get('type') == 'MultiPolygon':
            polys = [[ring(r) for r in p] for p in g['arcs']]
        out.append((g.get('id'), g['properties']['name'], polys))
    return out


def area_centroid(polys):
    """Centroid (lon, lat) of the largest polygon's outer ring (planar, good enough to place a dot)."""
    best, best_a = None, -1
    for p in polys:
        r = p[0]
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        if abs(a) > best_a:
            best_a = abs(a)
            best = (cx / (3 * a), cy / (3 * a)) if a else r[0]
    return best


def main(f110, f50, fiso):
    iso = {row['country-code']: row['alpha-2'] for row in csv.DictReader(open(fiso, encoding='utf-8'))}

    def code(gid, name):
        return NO_ID.get(name) if gid is None else iso.get(gid)

    big = [(code(i, n), p) for i, n, p in decode(json.load(open(f110, encoding='utf-8')))]
    small = [(code(i, n), p) for i, n, p in decode(json.load(open(f50, encoding='utf-8')))]
    big = [(c, p) for c, p in big if c and c not in SKIP and p]

    # projection bounds over the whole globe (so the map keeps its shape), then scale to WIDTH
    xmax, ymax = equal_earth(180, 0)[0], equal_earth(0, 90)[1]
    k = WIDTH / (2 * xmax)
    ymin = equal_earth(0, -60)[1]                      # cut below 60° S: nothing there without Antarctica
    height = round((ymax - ymin) * k)

    def px(lon, lat):
        x, y = equal_earth(lon, lat)
        return round((x + xmax) * k, 1), round((ymax - y) * k, 1)

    def unwrap(r):
        """Rings that cross the 180° meridian (Russia, Fiji) as one continuous ring, plus the copy shifted by
        360° that shows its other side: the map clips both to the globe's outline ("outline")."""
        out = [r[0]]
        for lon, lat in r[1:]:
            prev = out[-1][0]
            lon += 360 * round((prev - lon) / 360)
            out.append((lon, lat))
        lo, hi = min(x for x, _ in out), max(x for x, _ in out)
        rings = [out]
        if hi > 180:
            rings.append([(x - 360, y) for x, y in out])
        if lo < -180:
            rings.append([(x + 360, y) for x, y in out])
        return rings

    shapes = {}
    for c, polys in big:
        d = []
        for p in polys:
            for r in (u for ring in p for u in unwrap(ring)):
                pts, last = [], None
                for lon, lat in r:
                    q = px(lon, lat)
                    if q != last:
                        pts.append(q)
                        last = q
                if len(pts) >= 3:
                    d.append('M' + 'L'.join(f'{x:g},{y:g}' for x, y in pts) + 'Z')
        if d:
            shapes[c] = shapes.get(c, '') + ''.join(d)
    dots = {}
    for c, polys in small:
        if c and c not in shapes and c not in SKIP and polys:
            dots[c] = list(px(*area_centroid(polys)))
    edge = [px(180, lat) for lat in range(90, -61, -2)] + [px(-180, lat) for lat in range(-60, 91, 2)]
    outline = 'M' + 'L'.join(f'{x:g},{y:g}' for x, y in edge) + 'Z'
    OUT.write_text(json.dumps({'w': WIDTH, 'h': height, 'outline': outline, 'shapes': shapes, 'dots': dots},
                              separators=(',', ':'), sort_keys=True) + '\n', encoding='utf-8')
    print(f'{len(shapes)} shapes, {len(dots)} dots, {OUT.stat().st_size // 1024} KiB -> {OUT}')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
