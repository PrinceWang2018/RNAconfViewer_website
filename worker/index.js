// The Worker of www.rnaconfviewer.com. Everything is static (index.html, guide/, images/, _redirects) and is
// served by Cloudflare's static assets directly; only the two feedback addresses reach this script
// (run_worker_first in wrangler.jsonc):
//
//   POST /api/feedback     a comment from the Feedback tab -> D1 database FEEDBACK_DB   (feedback.js)
//   /admin/feedback        the comments, for the site owner (password)                  (admin.js)

import * as feedback from './feedback.js';
import * as admin from './admin.js';

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    const context = { request, env, ctx };
    if (pathname === '/api/feedback') {
      return request.method === 'POST' ? feedback.onRequestPost(context) : feedback.onRequest(context);
    }
    if (pathname === '/admin/feedback' || pathname === '/admin/feedback/') return admin.onRequest(context);
    return env.ASSETS.fetch(request);
  },
};
