import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const {
  normalizeProbeErrorCode,
  normalizeProbeForwardResponse,
} = require("../public/lzcapp-fetch-proxy.js") as {
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
};

describe("lzcapp-fetch-proxy probe normalization", () => {
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
});
