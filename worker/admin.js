// /admin/feedback — the comments sent from the Feedback tab, for the site owner only.
// (Part of the site's Worker, worker/index.js; setup in README.md, "Feedback".)
//
// Protected by HTTP basic authentication: user "admin", password = the secret FEEDBACK_ADMIN_PASSWORD of the
// Worker. Without that secret the page is closed. Actions (POST, same page): mark a comment read or
// new, delete it. ?format=csv downloads everything as a spreadsheet file.

import { SCHEMA } from './feedback.js';

const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function timingSafeEqual(a, b) {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

function authorised(request, env) {
  const pw = env.FEEDBACK_ADMIN_PASSWORD;
  if (!pw) return false;
  const h = request.headers.get('authorization') || '';
  if (!h.startsWith('Basic ')) return false;
  let decoded = '';
  try { decoded = atob(h.slice(6)); } catch { return false; }
  const i = decoded.indexOf(':');
  return i >= 0 && decoded.slice(0, i) === 'admin' && timingSafeEqual(decoded.slice(i + 1), pw);
}

const headers = { 'cache-control': 'no-store', 'x-robots-tag': 'noindex', 'x-frame-options': 'DENY',
  'content-security-policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'" };

function page(body, status = 200) {
  return new Response(`<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>RCV feedback</title>
<style>
body{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;font-size:14px;color:#222;margin:24px auto;max-width:1100px;padding:0 16px}
h1{font-size:22px;color:#1f4e8c} table{border-collapse:collapse;width:100%} th,td{border-bottom:1px solid #d9dde3;padding:8px;text-align:left;vertical-align:top}
th{background:#f4f6f9} td.msg{white-space:pre-wrap;word-break:break-word;max-width:520px} tr.new td{background:#fffbea}
.muted{color:#5c5c5c;font-size:12px} button{font-size:12px;margin:0 4px 4px 0;cursor:pointer} a{color:#1a5aa6}
</style></head><body>${body}</body></html>`, { status, headers: { ...headers, 'content-type': 'text/html; charset=utf-8' } });
}

function csvCell(v) { const s = String(v ?? ''); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }

export async function onRequest({ request, env }) {
  if (!authorised(request, env)) {
    return new Response(env.FEEDBACK_ADMIN_PASSWORD ? 'Sign in required.' : 'Not set up: add the secret FEEDBACK_ADMIN_PASSWORD.', {
      status: 401, headers: { ...headers, 'www-authenticate': 'Basic realm="RCV feedback", charset="UTF-8"' },
    });
  }
  const db = env.FEEDBACK_DB;
  if (!db) return page('<h1>RCV feedback</h1><p>The D1 database is not bound: add the binding <code>FEEDBACK_DB</code> (README.md, "Feedback").</p>', 503);
  await db.prepare(SCHEMA).run();
  const url = new URL(request.url);

  if (request.method === 'POST') {
    const form = await request.formData();
    const id = Number(form.get('id'));
    const action = form.get('action');
    if (Number.isInteger(id)) {
      if (action === 'delete') await db.prepare('DELETE FROM feedback WHERE id = ?').bind(id).run();
      else if (action === 'read' || action === 'new') await db.prepare('UPDATE feedback SET status = ? WHERE id = ?').bind(action, id).run();
    }
    return Response.redirect(url.origin + url.pathname + (url.search || ''), 303);
  }

  const { results } = await db.prepare('SELECT id, created, message, email, version, country, user_agent, status FROM feedback ORDER BY id DESC LIMIT 1000').all();

  if (url.searchParams.get('format') === 'csv') {
    const cols = ['id', 'created', 'status', 'email', 'country', 'version', 'message', 'user_agent'];
    const csv = '﻿' + [cols.join(','), ...results.map((r) => cols.map((c) => csvCell(r[c])).join(','))].join('\r\n');
    return new Response(csv, { headers: { ...headers, 'content-type': 'text/csv; charset=utf-8',
      'content-disposition': `attachment; filename="rcv-feedback-${new Date().toISOString().slice(0, 10)}.csv"` } });
  }

  const unread = results.filter((r) => r.status === 'new').length;
  const rows = results.map((r) => `<tr class="${r.status === 'new' ? 'new' : ''}">
<td>${r.id}<br><span class="muted">${esc(r.status)}</span></td>
<td>${esc(r.created.replace('T', ' ').slice(0, 16))} UTC<br><span class="muted">${esc(r.country || '')}</span></td>
<td>${r.email ? `<a href="mailto:${esc(r.email)}?subject=${encodeURIComponent('Your feedback on RCV')}">${esc(r.email)}</a>` : '<span class="muted">none</span>'}</td>
<td class="msg">${esc(r.message)}${r.version ? `<div class="muted">Version: ${esc(r.version)}</div>` : ''}<div class="muted">${esc(r.user_agent || '')}</div></td>
<td><form method="post"><input type="hidden" name="id" value="${r.id}">
<button name="action" value="${r.status === 'new' ? 'read' : 'new'}">Mark ${r.status === 'new' ? 'read' : 'new'}</button>
<button name="action" value="delete" onclick="return confirm('Delete this comment?')">Delete</button></form></td></tr>`).join('');

  return page(`<h1>RCV feedback</h1>
<p>${results.length} comment${results.length === 1 ? '' : 's'}, ${unread} new. <a href="?format=csv">Download as CSV</a> · <a href="/#feedback">Feedback tab</a></p>
<table><thead><tr><th>#</th><th>Received</th><th>Email</th><th>Comment</th><th></th></tr></thead>
<tbody>${rows || '<tr><td colspan="5" class="muted">No feedback yet.</td></tr>'}</tbody></table>`);
}
