// POST /api/feedback — stores a comment from the Feedback tab in the D1 database bound as FEEDBACK_DB.
// (Part of the site's Worker, worker/index.js; setup in README.md, "Feedback".)
//
// Body (JSON or form): message (required, up to 5,000 characters), email (optional), page, version, website
// (a hidden field that people leave empty; anything in it is a bot). One address may send at most 5 comments
// an hour. Only a salted hash of the address is stored, to enforce that limit; it cannot be turned back into
// the address.

const MAX_MESSAGE = 5000;
const MAX_EMAIL = 254;
const PER_HOUR = 5;

export const SCHEMA = `CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created TEXT NOT NULL,
  message TEXT NOT NULL,
  email TEXT,
  version TEXT,
  country TEXT,
  user_agent TEXT,
  ip_hash TEXT,
  status TEXT NOT NULL DEFAULT 'new'
)`;

function reply(status, body) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}

async function sha256(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

const clip = (v, n) => String(v ?? '').trim().slice(0, n);

export async function onRequestPost({ request, env }) {
  if (!env.FEEDBACK_DB) return reply(503, { ok: false, error: 'Feedback is not set up yet. Please send an email instead.' });

  let data = {};
  try {
    const type = request.headers.get('content-type') || '';
    if (type.includes('application/json')) data = await request.json();
    else data = Object.fromEntries(await request.formData());
  } catch {
    return reply(400, { ok: false, error: 'The form could not be read.' });
  }

  if (clip(data.website, 200)) return reply(200, { ok: true });          // honeypot: pretend it worked

  const message = clip(data.message, MAX_MESSAGE + 1);
  const email = clip(data.email, MAX_EMAIL + 1);
  if (message.length < 3) return reply(400, { ok: false, error: 'Please write a comment or suggestion.' });
  if (message.length > MAX_MESSAGE) return reply(400, { ok: false, error: `Please keep it under ${MAX_MESSAGE} characters.` });
  if (email && (email.length > MAX_EMAIL || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))) {
    return reply(400, { ok: false, error: 'The email address does not look right (it is optional; leave it empty).' });
  }

  const db = env.FEEDBACK_DB;
  await db.prepare(SCHEMA).run();
  const ip = request.headers.get('cf-connecting-ip') || '';
  const ipHash = ip ? (await sha256((env.FEEDBACK_SALT || 'rcv-feedback') + ip)).slice(0, 32) : null;
  const now = new Date();
  if (ipHash) {
    const since = new Date(now.getTime() - 3600e3).toISOString();
    const row = await db.prepare('SELECT COUNT(*) AS n FROM feedback WHERE ip_hash = ? AND created > ?').bind(ipHash, since).first();
    if (row && row.n >= PER_HOUR) return reply(429, { ok: false, error: 'Thank you — that is a lot of feedback for one hour. Please try again later.' });
  }

  await db.prepare('INSERT INTO feedback (created, message, email, version, country, user_agent, ip_hash) VALUES (?, ?, ?, ?, ?, ?, ?)')
    .bind(now.toISOString(), message, email || null, clip(data.version, 40) || null,
      (request.cf && request.cf.country) || null, clip(request.headers.get('user-agent'), 300) || null, ipHash)
    .run();
  return reply(200, { ok: true });
}

export function onRequest() {
  return reply(405, { ok: false, error: 'Use POST.' });
}
