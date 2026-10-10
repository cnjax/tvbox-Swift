#!/usr/bin/env python3
"""Smoke test: python3 smoke_test.py <config_url> [site key substring ...]  (bridge must be running)

Walks home -> category -> detail -> play for each type=3 site and prints one line per site.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode, urljoin

BRIDGE = os.environ.get('BRIDGE', 'http://127.0.0.1:9978')


def get(path, **q):
    url = f'{BRIDGE}{path}?{urlencode(q)}'
    req = urllib.request.Request(url)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=90) as r:
            return r.status, r.headers, r.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode('utf-8', 'ignore')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def check(cfg_url, site, spider):
    api = site['api'] if site['api'].startswith('csp_') else urljoin(cfg_url, site['api'])
    ext = site.get('ext', '')
    ext = json.dumps(ext, ensure_ascii=False) if isinstance(ext, (dict, list)) else str(ext)
    if ext.startswith(('./', '../')):
        ext = urljoin(cfg_url, ext)
    base = {'key': site['key'], 'api': api, 'jar': urljoin(cfg_url, spider), 'extend': ext}
    code, _, body = get('/vod', **base, filter='true')
    home = json.loads(body)
    assert code == 200, home
    classes = home.get('class') or []
    videos = home.get('list') or []
    if classes:
        _, _, body = get('/vod', **base, ac='detail', t=classes[0]['type_id'], pg='1', ext='e30=')
        videos = json.loads(body).get('list') or videos
    assert videos, f'no videos (classes={len(classes)})'
    _, _, body = get('/vod', **base, ac='detail', ids=videos[0]['vod_id'])
    detail = json.loads(body)['list'][0]
    first = detail['vod_play_url'].split('$$$')[0].split('#')[0].split('$', 1)[1]
    req = urllib.request.Request(first.replace('http://127.0.0.1:9978', BRIDGE))
    try:
        r = urllib.request.build_opener(NoRedirect).open(req, timeout=90)
        status, location = r.status, r.headers.get('Location')
    except urllib.error.HTTPError as e:
        status, location = e.code, e.headers.get('Location') or e.read().decode()[:200]
    assert status == 302, f'play {status}: {location}'
    return f'{len(classes)} classes, {len(videos)} videos, "{detail.get("vod_name")}" -> {location[:90]}'


def main():
    cfg_url = sys.argv[1]
    filters = sys.argv[2:]
    cfg = json.loads(urllib.request.urlopen(urllib.request.Request(cfg_url, headers={'User-Agent': 'okhttp/3.12.13'}), timeout=30).read())
    sites = [s for s in cfg['sites'] if s.get('type') == 3 and (not filters or any(f in s['key'] or f in s['name'] or f in s['api'] for f in filters))]
    ok = 0
    for site in sites:
        try:
            print(f'OK   {site["name"]}: {check(cfg_url, site, site.get("jar") or cfg.get("spider", ""))}', flush=True)
            ok += 1
        except Exception as e:
            print(f'FAIL {site["name"]}: {str(e)[:200]}', flush=True)
    print(f'{ok}/{len(sites)} passed')


if __name__ == '__main__':
    main()
