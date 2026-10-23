import { createRequire } from "node:module";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const {
  httpRequestFollowRedirects,
  normalizeProbeErrorCode,
  normalizeProbeForwardResponse,
  pickPassthroughHeaders,
} = require("../public/lzcapp-fetch-proxy.js") as {
  httpRequestFollowRedirects: (url: string, timeout: number, maxBytes: number) => Promise<{
    statusCode: number;
    body: Buffer;
  }>;
  normalizeProbeErrorCode: (text: string, statusCode: number) => string;
  normalizeProbeForwardResponse: (forwarded: {
    statusCode?: number;
    headers?: Record<string, string>;
    body?: Buffer;
  }) => {
    statusCode: number;
    headers: Record<string, string>;
    body: Buffer;
  };
  pickPassthroughHeaders: (
    headers?: Record<string, string | undefined>,
  ) => Record<string, string>;
};

describe("lzcapp-fetch-proxy probe normalization", () => {
  it("fetches a hostname with Node automatic address-family selection", async () => {
    const server = createServer((_req, res) => res.end("resolved"));
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    try {
      const port = (server.address() as AddressInfo).port;
      const response = await httpRequestFollowRedirects(`http://localhost:${port}/`, 2000, 1024);
      expect(response.statusCode).toBe(200);
      expect(response.body.toString()).toBe("resolved");
    } finally {
      await new Promise<void>((resolve, reject) => server.close((err) => err ? reject(err) : resolve()));
    }
  });

  it("classifies timeout signatures as TIMEOUT", () => {
    expect(normalizeProbeErrorCode("ETIMEDOUT timeout", 502)).toBe("TIMEOUT");
  });

  it("wraps non-json probe upstream failures into JSON envelopes", () => {
    const normalized = normalizeProbeForwardResponse({
      statusCode: 502,
      headers: {
        "content-type": "text/plain; charset=utf-8",
      },
      body: Buffer.from("ETIMEDOUT timeout\n", "utf8"),
    });

    expect(normalized.statusCode).toBe(502);
    expect(normalized.headers["content-type"]).toContain("application/json");
    expect(JSON.parse(normalized.body.toString("utf8"))).toMatchObject({
      ok: false,
      code: "TIMEOUT",
      message: "ETIMEDOUT timeout",
    });
  });

  it("keeps subscription diagnostics headers for import parity", () => {
    const picked = pickPassthroughHeaders({
      "subscription-userinfo": "upload=1; download=2; total=3; expire=4",
      "profile-title": "My Profile",
      "content-disposition": 'attachment; filename="demo.yaml"',
      server: "nginx",
    });

    expect(picked).toEqual({
      "subscription-userinfo": "upload=1; download=2; total=3; expire=4",
      "profile-title": "My Profile",
      "content-disposition": 'attachment; filename="demo.yaml"',
    });
  });
});
