// Runs FongMi-style "catvod" JS spiders (export default {...} / __jsEvalReturn) for bridge.py.
// stdin/stdout: one JSON object per line, same protocol as jar/JarBridge.java.
import crypto from 'node:crypto';
import fs from 'node:fs';
import readline from 'node:readline';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [dataDir, port] = process.argv.slice(2);
const require = createRequire(dataDir + '/');
console.log = console.info = console.debug = (...a) => console.error(...a);

globalThis.CryptoJS = require('crypto-js');
globalThis.md5X = (s) => crypto.createHash('md5').update(String(s)).digest('hex');
globalThis.__JS_SPIDER__ = null; // legacy scripts assign this implicit global
globalThis.getProxyUrl = () => `http://127.0.0.1:${port}/proxy?do=js`;
const store = new Map();
globalThis.local = {
  get: (rule, key) => store.get(`${rule}/${key}`) ?? '',
  set: (rule, key, value) => store.set(`${rule}/${key}`, value),
  delete: (rule, key) => store.delete(`${rule}/${key}`),
};

const DROP_HEADERS = new Set(['connection', 'keep-alive', 'host', 'content-length', 'transfer-encoding']);

globalThis.req = async (url, opt = {}) => {
  const method = (opt.method || 'GET').toUpperCase();
  const headers = Object.fromEntries(Object.entries(opt.headers || {}).filter(([k]) => !DROP_HEADERS.has(k.toLowerCase())));
  const has = (name) => Object.keys(headers).some((k) => k.toLowerCase() === name);
  let body = opt.body;
  if (body === undefined && opt.data !== undefined && method !== 'GET') {
    if (typeof opt.data === 'string') body = opt.data;
    else if (opt.postType === 'form') {
      body = new URLSearchParams(opt.data).toString();
      if (!has('content-type')) headers['Content-Type'] = 'application/x-www-form-urlencoded';
    } else {
      body = JSON.stringify(opt.data);
      if (!has('content-type')) headers['Content-Type'] = 'application/json';
    }
  } else if (body !== undefined && typeof body !== 'string') body = JSON.stringify(body);
  if (method === 'GET' || method === 'HEAD') body = undefined;
  try {
    const r = await fetch(url, {
      method, headers, body,
      redirect: opt.redirect === 0 || opt.redirect === false ? 'manual' : 'follow',
      signal: AbortSignal.timeout(opt.timeout || 15000),
    });
    const buf = Buffer.from(await r.arrayBuffer());
    const content = opt.buffer === 1 ? [...buf] : opt.buffer === 2 ? buf.toString('base64') : buf.toString('utf8');
    return { code: r.status, headers: Object.fromEntries(r.headers), content };
  } catch (e) {
    console.error('[js req]', url, e.message);
    return { code: 0, headers: {}, content: '' };
  }
};

const spiders = new Map();

async function load({ key, file, ext }) {
  // crypto-js is provided as a global; the relative import would not resolve here.
  const src = fs.readFileSync(file, 'utf8').replace(/^\s*import\s+[^;\n]*crypto-js[^;\n]*;?/gm, '');
  const runFile = file.replace(/\.mjs$/, '') + '.run.mjs';
  fs.writeFileSync(runFile, src);
  const mod = await import(pathToFileURL(runFile).href + '?t=' + Date.now());
  const cat = typeof mod.__jsEvalReturn === 'function';
  const sp = cat ? mod.__jsEvalReturn() : mod.default ?? globalThis.__JS_SPIDER__;
  if (!sp) throw new Error('no spider export');
  let parsed = ext;
  try { parsed = JSON.parse(ext); } catch {}
  await sp.init?.(cat ? { skey: key, stype: 3, ext: parsed } : parsed);
  return sp;
}

async function spider(req) {
  const id = `${req.key}\n${req.file}\n${req.ext}`;
  if (!spiders.has(id)) spiders.set(id, load(req));
  try {
    return await spiders.get(id);
  } catch (e) {
    spiders.delete(id);
    throw e;
  }
}

async function call(req) {
  const sp = await spider(req);
  const a = req.args || [];
  switch (req.method) {
    case 'home': return sp.home?.(a[0]);
    case 'homeVod': return sp.homeVod?.();
    case 'category': return sp.category?.(a[0], a[1], a[2], a[3] || {});
    case 'detail': return sp.detail?.(a[0][0]);
    case 'search': return sp.search?.(a[0], a[1], a[2] || '1');
    case 'play': return sp.play?.(a[0], a[1], a[2] || []);
    default: throw new Error('unknown method ' + req.method);
  }
}

readline.createInterface({ input: process.stdin }).on('line', async (line) => {
  const req = JSON.parse(line);
  let res;
  try {
    const result = await call(req);
    res = { id: req.id, result: result ?? '' };
  } catch (e) {
    console.error(e);
    res = { id: req.id, error: String(e?.message || e) };
  }
  process.stdout.write(JSON.stringify(res) + '\n');
});
