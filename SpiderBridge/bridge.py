#!/usr/bin/env python3
"""TVBox type=3 spider bridge for the macOS app.

Exposes every spider (py / js / jar) as a TVBox "type 4 remote" HTTP API on 127.0.0.1,
so the Swift app talks to them exactly like a remote source.

  GET /health
  GET /vod?key=&api=&jar=&extend=  + type-4 params (filter | t,pg,ext | ids | wd,quick)
  GET /play?key=&flag=&id=          -> playerContent, then 302 / header-proxy to the real stream
  GET /proxy?do=py&siteKey=...      -> spider localProxy
  GET /proxy?u=&h=                  -> stream proxy that injects spider-provided headers

py spiders run in-process, jar spiders in a JVM child (jar/JarBridge.java), js spiders in a node child (js/runner.mjs).
"""
import argparse
import base64
import glob
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urljoin, urlparse

RES = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # RES lives inside the signed app bundle
PY_DEPS = ['requests', 'lxml', 'pycryptodome', 'pyquery', 'beautifulsoup4', 'cryptography']
MAVEN = 'https://repo1.maven.org/maven2/'
JAR_LIBS = [
    'com/squareup/okhttp3/okhttp/3.12.13/okhttp-3.12.13.jar',
    'com/squareup/okio/okio/1.17.6/okio-1.17.6.jar',
    'com/google/code/gson/gson/2.11.0/gson-2.11.0.jar',
    'org/json/json/20240303/json-20240303.jar',
]
DEX2JAR_ZIP = 'https://github.com/pxb1988/dex2jar/releases/download/v2.4/dex-tools-v2.4.zip'
EXTRA_PATHS = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin']

args = None
log_lock = threading.Lock()


def log(*parts):
    with log_lock:
        print('[bridge]', *parts, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- environment

def ensure_venv():
    """Re-exec inside <data>/venv with the third-party packages py spiders import."""
    venv = os.path.join(args.data, 'venv')
    py = os.path.join(venv, 'bin', 'python3')
    if os.path.realpath(sys.prefix) == os.path.realpath(venv):
        return
    marker = os.path.join(venv, '.deps-' + '-'.join(PY_DEPS))
    if not os.path.exists(marker):
        log('creating python venv, first run may take a minute...')
        subprocess.check_call([sys.executable, '-m', 'venv', venv])
        subprocess.check_call([py, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', *PY_DEPS])
        open(marker, 'w').close()
    os.execv(py, [py, os.path.abspath(__file__), *sys.argv[1:]])


def which(name, extra=()):
    path = os.pathsep.join([os.environ.get('PATH', ''), *EXTRA_PATHS, *extra])
    return shutil.which(name, path=path)


def http_get(url, headers=None, timeout=30):
    url = quote(url, safe=":/?&=%#@+,;~!$'()*[]")  # spider paths are often Chinese
    req = urllib.request.Request(url, headers={'User-Agent': 'okhttp/3.12.13', **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cached_download(url, suffix=''):
    """Download once per bridge process; keep the previous copy if the network fails."""
    path = os.path.join(args.data, 'cache', hashlib.md5(url.encode()).hexdigest() + suffix)
    if path in cached_download.done:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        data = http_get(url)
        tmp = f'{path}.{threading.get_ident()}.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        if not os.path.exists(path):
            raise
        log('download failed, using cached copy of', url)
    cached_download.done.add(path)
    return path


cached_download.done = set()


def to_obj(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode('utf-8', 'ignore')
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


# ---------------------------------------------------------------- runners

class PyRunner:
    def __init__(self, site):
        if os.path.join(RES, 'py') not in sys.path:
            sys.path.insert(0, os.path.join(RES, 'py'))
        import base.spider as base
        base.PROXY_BASE = f'http://127.0.0.1:{args.port}'
        path = cached_download(site['api'], '.py')
        spec = importlib.util.spec_from_file_location('spider_' + hashlib.md5(site['key'].encode()).hexdigest(), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.spider = module.Spider()
        self.spider.siteKey = site['key']
        self.spider.init(site['extend'])

    def call(self, method, *a):
        s = self.spider
        if method == 'home':
            return s.homeContent(*a)
        if method == 'homeVod':
            return s.homeVideoContent()
        if method == 'category':
            return s.categoryContent(*a)
        if method == 'detail':
            return s.detailContent(*a)
        if method == 'search':
            n = len(inspect.signature(s.searchContent).parameters)
            return s.searchContent(*a[:n])
        if method == 'play':
            return s.playerContent(*a)
        if method == 'proxy':
            return s.localProxy(*a)
        raise ValueError(method)


class ChildProcess:
    """JSON-lines RPC to a long-lived child process (JVM or node)."""

    def __init__(self, name, cmd, cwd=None):
        self.name, self.cmd, self.cwd = name, cmd, cwd
        self.proc = None
        self.lock = threading.Lock()
        self.pending = {}
        self.next_id = 0

    def _start(self):
        log('starting', self.name)
        self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=sys.stderr, text=True, encoding='utf-8', bufsize=1)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            slot = self.pending.pop(msg.get('id'), None)
            if slot:
                slot[1].update(msg)
                slot[0].set()
        for event, _ in list(self.pending.values()):
            event.set()

    def call(self, payload, timeout=60):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            self.next_id += 1
            payload = {**payload, 'id': self.next_id}
            slot = (threading.Event(), {})
            self.pending[self.next_id] = slot
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
        if not slot[0].wait(timeout):
            self.pending.pop(payload['id'], None)
            raise TimeoutError(f'{self.name} timed out')
        if 'error' in slot[1]:
            raise RuntimeError(slot[1]['error'])
        if 'result' not in slot[1]:
            raise RuntimeError(f'{self.name} exited')
        return slot[1]['result']


_jvm = None
_node = None
_child_lock = threading.Lock()


def jvm():
    global _jvm
    with _child_lock:
        if _jvm:
            return _jvm
        java_home = subprocess.run(['/usr/libexec/java_home'], capture_output=True, text=True).stdout.strip()
        extra = [os.path.join(java_home, 'bin')] if java_home else []
        java, javac = which('java', extra), which('javac', extra)
        if not java or not javac:
            raise RuntimeError('jar 源需要 JDK 11+（未找到 java/javac），可执行: brew install openjdk')
        base = os.path.join(args.data, 'jar')
        lib = os.path.join(base, 'lib')
        os.makedirs(lib, exist_ok=True)
        for rel in JAR_LIBS:
            dst = os.path.join(lib, os.path.basename(rel))
            if not os.path.exists(dst):
                log('downloading', rel)
                with open(dst + '.tmp', 'wb') as f:
                    f.write(http_get(MAVEN + rel, timeout=120))
                os.replace(dst + '.tmp', dst)
        sources = glob.glob(os.path.join(RES, 'jar', '**', '*.java'), recursive=True)
        digest = hashlib.md5(b''.join(open(s, 'rb').read() for s in sorted(sources))).hexdigest()
        classes = os.path.join(base, 'classes-' + digest)
        if not os.path.isdir(classes):
            log('compiling jar bridge')
            subprocess.check_call([javac, '-nowarn', '-encoding', 'UTF-8', '-cp', os.path.join(lib, '*'),
                                   '-d', classes + '.tmp', *sources])
            os.replace(classes + '.tmp', classes)
        # Spider jars reference classes their Android host provides; ART verifies lazily, HotSpot eagerly,
        # so verification is off to only fail when such code actually runs.
        cmd = [java, '-XX:+UnlockDiagnosticVMOptions', '-XX:-BytecodeVerificationRemote',
               '-Djava.net.useSystemProxies=true', f'-Dbridge.port={args.port}', f'-Dbridge.data={base}', '-Dfile.encoding=UTF-8',
               '-cp', classes + os.pathsep + os.path.join(lib, '*'), 'JarBridge']
        _jvm = ChildProcess('jvm', cmd)
        _jvm.java = java
        return _jvm


_d2j_lock = threading.Lock()


def dex2jar(jar_url):
    """Spider jars are Android dex; convert to JVM bytecode once per jar content."""
    proc = jvm()
    with _d2j_lock:
        return _dex2jar(proc, jar_url)


def _dex2jar(proc, jar_url):
    src = cached_download(jar_url, '.jar')
    digest = hashlib.md5(open(src, 'rb').read()).hexdigest()
    out = os.path.join(args.data, 'jar', 'converted', digest + '.jar')
    if os.path.exists(out):
        return out
    tools = os.path.join(args.data, 'jar', 'dex-tools')
    if not glob.glob(os.path.join(tools, '*', 'lib')):
        log('downloading dex2jar')
        zpath = tools + '.zip'
        with open(zpath, 'wb') as f:
            f.write(http_get(DEX2JAR_ZIP, timeout=300))
        zipfile.ZipFile(zpath).extractall(tools)
        os.remove(zpath)
    d2j_lib = glob.glob(os.path.join(tools, '*', 'lib'))[0]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    log('converting dex -> jar', jar_url)
    subprocess.check_call([proc.java, '-cp', os.path.join(d2j_lib, '*'), 'com.googlecode.dex2jar.tools.Dex2jarCmd',
                           '-f', '-o', out + '.tmp.jar', src], stdout=sys.stderr)
    os.replace(out + '.tmp.jar', out)
    return out


def node():
    global _node
    with _child_lock:
        if _node:
            return _node
        nvm = sorted(glob.glob(os.path.expanduser('~/.nvm/versions/node/*/bin')), reverse=True)
        node_bin = which('node', nvm)
        if not node_bin:
            raise RuntimeError('js 源需要 Node.js 18+（未找到 node）')
        base = os.path.join(args.data, 'js')
        if not os.path.isdir(os.path.join(base, 'node_modules', 'crypto-js')):
            npm = os.path.join(os.path.dirname(node_bin), 'npm')
            os.makedirs(base, exist_ok=True)
            log('installing crypto-js')
            env = {**os.environ, 'PATH': os.path.dirname(node_bin) + os.pathsep + os.environ.get('PATH', '')}
            subprocess.check_call([npm, 'install', '--silent', '--prefix', base, 'crypto-js'], env=env, stdout=sys.stderr)
        _node = ChildProcess('node', [node_bin, os.path.join(RES, 'js', 'runner.mjs'), base, str(args.port)])
        return _node


class ChildRunner:
    def __init__(self, site, kind):
        self.kind, self.site = kind, site
        if kind == 'jar':
            self.child = jvm()
            self.payload = {'key': site['key'], 'jar': dex2jar(site['jar']), 'api': site['api'], 'ext': site['extend']}
        else:
            self.child = node()
            self.payload = {'key': site['key'], 'file': cached_download(site['api'], '.mjs'),
                            'api': site['api'], 'ext': site['extend']}

    def call(self, method, *a):
        if method == 'proxy':
            raise RuntimeError(f'{self.kind} proxy not supported')
        return self.child.call({**self.payload, 'method': method, 'args': list(a)})


SITES = {}       # key -> site params, filled by /vod so /play and /proxy can find the spider
RECENT_PY = ['']  # proxy urls without siteKey go to the last used py spider, like the Android host
RUNNERS = {}
_init_locks = {}
_runner_lock = threading.Lock()


def runner(site):
    ident = json.dumps(site, sort_keys=True)
    with _runner_lock:
        lock = _init_locks.setdefault(ident, threading.Lock())
    with lock:  # one init per site, different sites init in parallel
        if ident not in RUNNERS:
            api = site['api']
            path = urlparse(api).path.lower()
            if api.startswith('csp_'):
                RUNNERS[ident] = ChildRunner(site, 'jar')
            elif path.endswith('.py'):
                RUNNERS[ident] = PyRunner(site)
            elif path.endswith('.js'):
                RUNNERS[ident] = ChildRunner(site, 'js')
            else:
                raise RuntimeError(f'unsupported spider api: {api}')
        return RUNNERS[ident]


# ---------------------------------------------------------------- type-4 API

def rewrite_play_urls(key, data):
    """Point every episode at /play so the player triggers playerContent lazily."""
    for vod in data.get('list') or []:
        flags = str(vod.get('vod_play_from') or '').split('$$$')
        groups = str(vod.get('vod_play_url') or '').split('$$$')
        out = []
        for i, group in enumerate(groups):
            flag = flags[i] if i < len(flags) else ''
            eps = []
            for j, ep in enumerate(group.split('#')):
                if not ep:
                    continue
                name, _, ident = ep.partition('$') if '$' in ep else (str(j + 1), '', ep)
                url = f'http://127.0.0.1:{args.port}/play?key={quote(key)}&flag={quote(flag)}&id={quote(ident)}'
                eps.append(f'{name}${url}')
            out.append('#'.join(eps))
        vod['vod_play_url'] = '$$$'.join(out)
    return data


def handle_vod(q):
    site = {'key': q.get('key', ''), 'api': q.get('api', ''), 'jar': q.get('jar', ''), 'extend': q.get('extend', '')}
    SITES[site['key']] = site
    r = runner(site)
    if isinstance(r, PyRunner):
        RECENT_PY[0] = site['key']
    if 'wd' in q:
        return to_obj(r.call('search', q['wd'], q.get('quick') == 'true', q.get('pg', '1')))
    if 'ids' in q:
        return rewrite_play_urls(site['key'], to_obj(r.call('detail', [q['ids']])))
    if 't' in q:
        ext = {}
        if q.get('ext'):
            try:
                ext = json.loads(base64.b64decode(q['ext']).decode())
            except Exception:
                pass
        return to_obj(r.call('category', q['t'], q.get('pg', '1'), True, ext))
    home = to_obj(r.call('home', True))
    if not home.get('list'):
        try:
            home['list'] = to_obj(r.call('homeVod')).get('list') or []
        except Exception as e:
            log('homeVideoContent failed:', e)
    return home


PLAY_CACHE = {}
HEADERS = {}     # token -> header dict for /proxy?u=


def resolve_play(q):
    key, flag, ident = q.get('key', ''), q.get('flag', ''), q.get('id', '')
    cache_key = (key, flag, ident)
    hit = PLAY_CACHE.get(cache_key)
    if hit and hit[0] > time.time():
        return hit[1]
    site = SITES.get(key)
    if not site:
        raise RuntimeError('spider not loaded, reopen the detail page')
    r = runner(site)
    if isinstance(r, PyRunner):
        RECENT_PY[0] = key
    res = to_obj(r.call('play', flag, ident, []))
    url = res.get('url') or ''
    if isinstance(url, list):  # ["name", "url", "name2", "url2"...]
        url = url[1] if len(url) > 1 else (url[0] if url else '')
    url = (res.get('playUrl') or '') + url
    headers = res.get('header') or res.get('headers') or {}
    if isinstance(headers, str):
        headers = to_obj(headers)
    if not url:
        raise RuntimeError('playerContent returned no url')
    if (res.get('parse') == 1 or res.get('jx') == 1) and not any(x in url for x in ('.m3u8', '.mp4', '.flv')):
        # ponytail: no webview sniffing / parse interfaces; such episodes will fail to play.
        log('episode needs sniffing/parse, passing page url through:', url)
    if url.startswith('/') or url.startswith('proxy://'):
        url = f'http://127.0.0.1:{args.port}' + url.replace('proxy://', '/proxy?')
    if headers and not url.startswith('http://127.0.0.1:'):  # local proxy urls handle headers themselves
        token = hashlib.md5(json.dumps(headers, sort_keys=True).encode()).hexdigest()[:12]
        HEADERS[token] = headers
        url = f'http://127.0.0.1:{args.port}/proxy?h={token}&u={quote(url, safe="")}'
    PLAY_CACHE[cache_key] = (time.time() + 300, url)
    return url


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *a):
        pass

    def send(self, code, body=b'', ctype='application/json; charset=utf-8', headers=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        headers = dict(headers or {})
        # AVPlayer refuses mp4 over HTTP without byte-range support ("Operation Stopped").
        rng = self.headers.get('Range', '') if code == 200 and body else ''
        if rng.startswith('bytes=') and ',' not in rng:
            first, _, last = rng[6:].strip().partition('-')
            n = len(body)
            start = int(first) if first else max(n - int(last or 0), 0)
            end = min(int(last), n - 1) if first and last else n - 1
            if start >= n or start > end:
                code, body, headers = 416, b'', {'Content-Range': f'bytes */{n}'}
            else:
                code, body = 206, body[start:end + 1]
                headers['Content-Range'] = f'bytes {start}-{end}/{n}'
            headers['Accept-Ranges'] = 'bytes'
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        try:
            if url.path == '/health':
                return self.send(200, '{"ok":true}')
            if url.path == '/vod':
                return self.send(200, json.dumps(handle_vod(q), ensure_ascii=False))
            if url.path == '/play':
                return self.send(302, b'', 'text/plain', {'Location': resolve_play(q)})
            if url.path == '/proxy':
                return self.proxy(q)
            self.send(404, '{}')
        except (BrokenPipeError, ConnectionResetError):
            pass  # player cancelled the request
        except Exception as e:
            traceback.print_exc()
            self.send(500, json.dumps({'error': str(e)}, ensure_ascii=False))

    def proxy(self, q):
        if q.get('do') == 'py':
            site = SITES.get(q.get('siteKey') or RECENT_PY[0])
            if not site:
                return self.send(404, 'unknown siteKey', 'text/plain')
            res = runner(site).call('proxy', q)
            if not res:
                return self.send(404, '', 'text/plain')
            code, mime, body = res[0], res[1], res[2]
            headers = res[3] if len(res) > 3 and isinstance(res[3], dict) else {}
            if hasattr(body, 'read'):
                body = body.read()
            elif hasattr(body, 'content'):
                body = body.content
            headers = {k: v for k, v in headers.items() if k.lower() not in ('content-length', 'content-type')}
            return self.send(int(code), body or b'', mime or 'application/octet-stream', headers)
        return self.stream(q['u'], HEADERS.get(q.get('h', ''), {}), q.get('h', ''))

    def stream(self, target, headers, token):
        import requests
        fwd = dict(headers)
        if self.headers.get('Range'):
            fwd['Range'] = self.headers['Range']
        r = requests.get(target, headers=fwd, stream=True, timeout=30, allow_redirects=True)
        ctype = r.headers.get('Content-Type', '')
        if 'mpegurl' in ctype.lower() or urlparse(r.url).path.endswith('.m3u8'):
            text = r.text
            base = r.url

            def wrap(u):
                return f'http://127.0.0.1:{args.port}/proxy?h={token}&u={quote(urljoin(base, u), safe="")}'

            lines = []
            for line in text.splitlines():
                s = line.strip()
                if s and not s.startswith('#'):
                    line = wrap(s)
                elif 'URI="' in line:
                    head, _, rest = line.partition('URI="')
                    uri, _, tail = rest.partition('"')
                    line = f'{head}URI="{wrap(uri)}"{tail}'
                lines.append(line)
            return self.send(200, '\n'.join(lines), 'application/vnd.apple.mpegurl')
        self.send_response(r.status_code)
        for k in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
            if k in r.headers:
                self.send_header(k, r.headers[k])
        self.end_headers()
        if self.command == 'HEAD':
            return r.close()
        try:
            for chunk in r.raw.stream(64 * 1024, decode_content=False):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            r.close()


def watch_parent(ppid):
    while True:
        time.sleep(2)
        if os.getppid() != ppid:
            os._exit(0)


def main():
    global args
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=9978)
    p.add_argument('--data', default=os.path.expanduser('~/Library/Application Support/TVBox/spider'))
    p.add_argument('--watch-parent', action='store_true', help='exit when the launching app goes away')
    args = p.parse_args()
    os.makedirs(args.data, exist_ok=True)
    ensure_venv()
    if args.watch_parent:
        threading.Thread(target=watch_parent, args=(os.getppid(),), daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    log(f'listening on 127.0.0.1:{args.port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
