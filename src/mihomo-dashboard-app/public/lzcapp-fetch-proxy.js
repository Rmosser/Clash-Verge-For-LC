#!/usr/bin/env node
"use strict";

// Same-origin fetch proxy for the dashboard to bypass browser CORS.
//
// Routes (when mounted under /fetch/):
// - GET /healthz
// - GET /?url=<encoded>
// - POST /probe

const http = require("http");
const https = require("https");
const dns = require("dns");
const net = require("net");
const { URL } = require("url");

const PORT = parseInt(process.env.PORT || "3001", 10);
const TIMEOUT_MS = parseInt(process.env.TIMEOUT_MS || "25000", 10);
const MAX_BYTES = parseInt(process.env.MAX_BYTES || String(12 * 1024 * 1024), 10);
const ALLOW_LOOPBACK = String(process.env.ALLOW_LOOPBACK || "") === "1";
const VERGE_API_BASE = process.env.VERGE_API_BASE || "http://host.lzcapp:9091";

const UA = "lzc-mihomo-dashboard-fetchproxy/0.1";

try {
  if (typeof dns.setDefaultResultOrder === "function") {
    dns.setDefaultResultOrder("ipv4first");
  }
} catch (_e) {}

function ipv4FirstLookup(hostname, options, callback) {
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
      "content-length": String(buf.length)
    },
    buf
  );
}

function pickPassthroughHeaders(headers) {
  const out = {};
  if (!headers || typeof headers !== "object") return out;

  const keys = [
    "subscription-userinfo",
    "profile-title",
    "x-profile-title",
    "content-disposition"
  ];

  for (const key of keys) {
    const value = headers[key];
    if (value === undefined || value === null) continue;
    out[key] = String(value);
  }
  return out;
}

function probeEnvelope(code, message, extra) {
  return JSON.stringify({
    ok: false,
    code,
    message,
    durationMs: 0,
    fromCache: false,
    ...(extra && typeof extra === "object" ? extra : {})
  });
}

function normalizeProbeErrorCode(text, statusCode) {
  const source = String(text || "").toUpperCase();
  if (source.includes("ETIMEDOUT") || source.includes("TIMEOUT")) {
    return "TIMEOUT";
  }
  if (
    source.includes("ECONNREFUSED") ||
    source.includes("ECONNRESET") ||
    source.includes("EHOSTUNREACH") ||
    source.includes("ENETUNREACH")
  ) {
    return "PROXY_UNREACHABLE";
  }
  if (source.includes("TLS") || source.includes("SSL")) {
    return "UPSTREAM_TLS";
  }
  if (statusCode === 401) {
    return "UNKNOWN";
  }
  return "UNKNOWN";
}

function sendProbeJson(res, statusCode, code, message, extra) {
  const body = probeEnvelope(code, message, extra);
  send(
    res,
    statusCode,
    {
      "content-type": "application/json; charset=utf-8",
      "content-length": String(Buffer.byteLength(body))
    },
    Buffer.from(body, "utf8")
  );
}

function normalizeProbeForwardResponse(forwarded) {
  const statusCode = forwarded.statusCode || 502;
  const contentType =
    forwarded.headers && forwarded.headers["content-type"]
      ? String(forwarded.headers["content-type"])
      : "";
  const bodyText = forwarded.body
    ? forwarded.body.toString("utf8").trim()
    : "";

  if (contentType.includes("application/json")) {
    return {
      statusCode,
      headers: {
        "content-type": contentType || "application/json; charset=utf-8"
      },
      body: forwarded.body || Buffer.alloc(0)
    };
  }

  const code = normalizeProbeErrorCode(bodyText, statusCode);
  return {
    statusCode,
    headers: { "content-type": "application/json; charset=utf-8" },
    body: Buffer.from(
      probeEnvelope(code, bodyText || `probe upstream failed (${statusCode})`),
      "utf8"
    )
  };
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

function readBody(req, maxBytes) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;

    req.on("data", (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(Object.assign(new Error("request too large"), { code: "ETOOBIG" }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on("end", () => {
      resolve(Buffer.concat(chunks, total));
    });

    req.on("error", (err) => {
      reject(err);
    });
  });
}

function performRequest(targetUrl, options) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(targetUrl);
    } catch (_e) {
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
        method: options.method || "GET",
        headers: options.headers || {
          "user-agent": UA,
          accept: "*/*",
          "accept-encoding": "identity"
        },
        lookup: ipv4FirstLookup
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
          if (total > options.maxBytes) {
            tooLarge = true;
            req.destroy();
            resp.destroy();
            return;
          }
          chunks.push(chunk);
        });

        resp.on("end", () => {
          if (tooLarge) {
            resolve({
              statusCode: 413,
              headers: { "content-type": "text/plain; charset=utf-8" },
              body: Buffer.from("response too large\n")
            });
            return;
          }
          resolve({ statusCode, headers, body: Buffer.concat(chunks, total) });
        });
      }
    );

    req.on("timeout", () => {
      req.destroy(Object.assign(new Error("timeout"), { code: "ETIMEDOUT" }));
    });
    req.setTimeout(options.timeoutMs);

    req.on("error", (err) => {
      reject(err);
    });

    if (options.body && options.body.length) {
      req.write(options.body);
    }
    req.end();
  });
}

async function httpRequestFollowRedirects(targetUrl, timeoutMs, maxBytes) {
  let current = targetUrl;
  for (let i = 0; i < 5; i += 1) {
    const out = await performRequest(current, {
      method: "GET",
      timeoutMs,
      maxBytes,
      headers: {
        "user-agent": UA,
        accept: "*/*",
        "accept-encoding": "identity"
      }
    });
    const sc = out.statusCode || 0;
    if (sc >= 300 && sc < 400 && out.headers && out.headers.location) {
      try {
        const next = new URL(
          String(out.headers.location),
          new URL(current)
        ).toString();
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
    body: Buffer.from("too many redirects\n")
  };
}

async function forwardProbe(req, res) {
  if ((req.method || "GET").toUpperCase() !== "POST") {
    sendText(res, 405, "method not allowed\n");
    return;
  }

  const body = await readBody(req, MAX_BYTES);
  const target = new URL("/probe", VERGE_API_BASE).toString();
  const forwarded = await performRequest(target, {
    method: "POST",
    body,
    timeoutMs: TIMEOUT_MS,
    maxBytes: MAX_BYTES,
    headers: {
      "user-agent": UA,
      accept: "application/json",
      "accept-encoding": "identity",
      "content-type": req.headers["content-type"] || "application/json",
      "content-length": String(body.length),
      ...(req.headers.cookie ? { cookie: req.headers.cookie } : {}),
      ...(req.headers.authorization
        ? { authorization: req.headers.authorization }
        : {})
    }
  });

  const normalized = normalizeProbeForwardResponse(forwarded);
  send(
    res,
    normalized.statusCode,
    normalized.headers,
    normalized.body || Buffer.alloc(0)
  );
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url || "/", "http://127.0.0.1");
    const pathname = u.pathname || "/";

    if (pathname === "/healthz") {
      sendText(res, 200, "ok\n");
      return;
    }

    if (pathname === "/probe") {
      await forwardProbe(req, res);
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

    const out = await httpRequestFollowRedirects(
      target.toString(),
      TIMEOUT_MS,
      MAX_BYTES
    );
    const ct =
      out.headers && out.headers["content-type"]
        ? String(out.headers["content-type"])
        : "text/plain; charset=utf-8";

    send(
      res,
      out.statusCode || 502,
      {
        "content-type": ct,
        "content-length": String((out.body && out.body.length) || 0),
        ...pickPassthroughHeaders(out.headers)
      },
      out.body || Buffer.alloc(0)
    );
  } catch (err) {
    const msg =
      (err && err.code ? String(err.code) + " " : "") +
      String((err && err.message) || err || "error");
    if ((req.url || "").startsWith("/probe")) {
      sendProbeJson(res, 502, normalizeProbeErrorCode(msg, 502), msg);
      return;
    }
    sendText(res, 502, msg + "\n");
  }
});

if (require.main === module) {
  server.listen(PORT, "0.0.0.0", () => {
    console.log(`[fetchproxy] listening on :${PORT}`);
  });
}

module.exports = {
  normalizeProbeErrorCode,
  normalizeProbeForwardResponse,
  pickPassthroughHeaders,
  probeEnvelope
};
