#!/usr/bin/env node
"use strict";

// Same-origin fetch proxy for the dashboard to bypass browser CORS.
//
// Routes (when mounted under /fetch/):
// - GET /healthz
// - GET /?url=<encoded>

const http = require("http");
const https = require("https");
const dns = require("dns");
const net = require("net");
const { URL } = require("url");

const PORT = parseInt(process.env.PORT || "3001", 10);
const TIMEOUT_MS = parseInt(process.env.TIMEOUT_MS || "25000", 10);
const MAX_BYTES = parseInt(process.env.MAX_BYTES || String(12 * 1024 * 1024), 10);
const ALLOW_LOOPBACK = String(process.env.ALLOW_LOOPBACK || "") === "1";

const UA = "lzc-mihomo-dashboard-fetchproxy/0.1";

// Prefer IPv4 when the subscription host is dual-stack. This avoids "hangs" on
// V4-only egress environments where the IPv6 connect attempt can take a full
// timeout window.
try {
  if (typeof dns.setDefaultResultOrder === "function") {
    dns.setDefaultResultOrder("ipv4first");
  }
} catch (_e) {}

function ipv4FirstLookup(hostname, options, callback) {
  // Node may pass (hostname, family, cb) on older versions.
  if (typeof options === "function") {
    callback = options;
    options = {};
  }

  dns.lookup(hostname, { all: true }, (err, addresses) => {
    if (err) return callback(err);
    if (!addresses || !addresses.length) {
      const e = Object.assign(new Error("no address"), { code: "ENOTFOUND" });
      return callback(e);
    }

    // Pick the first IPv4 if available, otherwise the first entry.
    let chosen = addresses[0];
    for (const a of addresses) {
      if (a && a.family === 4) {
        chosen = a;
        break;
      }
    }
    return callback(null, chosen.address, chosen.family);
  });
}

function send(res, statusCode, headers, bodyBuf) {
  res.statusCode = statusCode;
  res.setHeader("cache-control", "no-store");
  if (headers) {
    for (const [k, v] of Object.entries(headers)) {
      if (v === undefined || v === null) continue;
      try {
        res.setHeader(k, v);
      } catch (_e) {}
    }
  }
  res.end(bodyBuf || Buffer.alloc(0));
}

function sendText(res, statusCode, text) {
  const buf = Buffer.from(String(text || ""), "utf8");
  send(
    res,
    statusCode,
    {
      "content-type": "text/plain; charset=utf-8",
      "content-length": String(buf.length),
    },
    buf
  );
}

function isLoopbackHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  if (!host) return false;
  if (host === "localhost" || host.endsWith(".localhost")) return true;

  const ipType = net.isIP(host);
  if (ipType === 4) {
    if (host === "0.0.0.0") return true;
    if (host.startsWith("127.")) return true;
    return false;
  }
  if (ipType === 6) {
    const clean = host.replace(/^\[|\]$/g, "");
    if (clean === "::1" || clean === "0:0:0:0:0:0:0:1") return true;
    return false;
  }
  return false;
}

function httpRequestOnce(targetUrl, timeoutMs, maxBytes) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(targetUrl);
    } catch (e) {
      reject(Object.assign(new Error("invalid url"), { code: "EINVAL" }));
      return;
    }

    const lib = u.protocol === "https:" ? https : http;
    const req = lib.request(
      {
        protocol: u.protocol,
        hostname: u.hostname,
        port: u.port || undefined,
        path: u.pathname + u.search,
        method: "GET",
        headers: {
          "user-agent": UA,
          accept: "*/*",
          // Keep response as plain bytes to simplify size accounting.
          "accept-encoding": "identity",
        },
        lookup: ipv4FirstLookup,
      },
      (resp) => {
        const statusCode = resp.statusCode || 0;
        const headers = resp.headers || {};

        const chunks = [];
        let total = 0;
        let tooLarge = false;

        resp.on("data", (chunk) => {
          if (tooLarge) return;
          total += chunk.length;
          if (total > maxBytes) {
            tooLarge = true;
            // Force-close; we'll map to 413.
            req.destroy();
            resp.destroy();
            return;
          }
          chunks.push(chunk);
        });

        resp.on("end", () => {
          if (tooLarge) {
            resolve({ statusCode: 413, headers: { "content-type": "text/plain; charset=utf-8" }, body: Buffer.from("response too large\n") });
            return;
          }
          resolve({ statusCode, headers, body: Buffer.concat(chunks, total) });
        });
      }
    );

    req.on("timeout", () => {
      req.destroy(Object.assign(new Error("timeout"), { code: "ETIMEDOUT" }));
    });
    req.setTimeout(timeoutMs);

    req.on("error", (err) => {
      reject(err);
    });

    req.end();
  });
}

async function httpRequestFollowRedirects(targetUrl, timeoutMs, maxBytes) {
  let current = targetUrl;
  for (let i = 0; i < 5; i += 1) {
    const out = await httpRequestOnce(current, timeoutMs, maxBytes);
    const sc = out.statusCode || 0;
    if (sc >= 300 && sc < 400 && out.headers && out.headers.location) {
      try {
        const next = new URL(String(out.headers.location), new URL(current)).toString();
        current = next;
        continue;
      } catch (_e) {
        return out;
      }
    }
    return out;
  }
  return {
    statusCode: 508,
    headers: { "content-type": "text/plain; charset=utf-8" },
    body: Buffer.from("too many redirects\n"),
  };
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url || "/", "http://127.0.0.1");
    const pathname = u.pathname || "/";

    if (pathname === "/healthz") {
      sendText(res, 200, "ok\n");
      return;
    }

    if ((req.method || "GET").toUpperCase() !== "GET") {
      sendText(res, 405, "method not allowed\n");
      return;
    }

    const raw = u.searchParams.get("url") || "";
    if (!raw) {
      sendText(res, 400, "missing url\n");
      return;
    }

    let target;
    try {
      target = new URL(raw);
    } catch (_e) {
      sendText(res, 400, "invalid url\n");
      return;
    }

    if (target.protocol !== "http:" && target.protocol !== "https:") {
      sendText(res, 400, "unsupported scheme\n");
      return;
    }

    if (!ALLOW_LOOPBACK && isLoopbackHost(target.hostname)) {
      sendText(res, 403, "loopback blocked\n");
      return;
    }

    const out = await httpRequestFollowRedirects(target.toString(), TIMEOUT_MS, MAX_BYTES);
    const ct = out.headers && out.headers["content-type"] ? String(out.headers["content-type"]) : "text/plain; charset=utf-8";

    send(
      res,
      out.statusCode || 502,
      {
        "content-type": ct,
        "content-length": String((out.body && out.body.length) || 0),
      },
      out.body || Buffer.alloc(0)
    );
  } catch (err) {
    const msg = (err && err.code ? String(err.code) + " " : "") + String((err && err.message) || err || "error");
    sendText(res, 502, msg + "\n");
  }
});

server.listen(PORT, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`[fetchproxy] listening on :${PORT}`);
});
