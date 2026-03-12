import { afterEach, describe, expect, it, vi } from "vitest";

import { probeRuntime } from "./runtime-probe";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("probeRuntime", () => {
  it("maps plain-text timeout failures into structured probe errors", async () => {
    vi.stubGlobal("window", {
      __LZCAPP_MIHOMO__: {
        vergeApiBaseUrl: "/verge-api",
      },
    } as typeof globalThis & {
      __LZCAPP_MIHOMO__?: {
        vergeApiBaseUrl?: string;
      };
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("ETIMEDOUT timeout\n", {
          status: 502,
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
          },
        }),
      ),
    );

    await expect(
      probeRuntime({
        kind: "ip_info",
        timeoutMs: 5000,
      }),
    ).rejects.toMatchObject({
      code: "TIMEOUT",
      message: "ETIMEDOUT timeout",
    });
  });

  it("preserves successful JSON envelopes from the probe backend", async () => {
    vi.stubGlobal("window", {
      __LZCAPP_MIHOMO__: {
        vergeApiBaseUrl: "/verge-api",
      },
    } as typeof globalThis & {
      __LZCAPP_MIHOMO__?: {
        vergeApiBaseUrl?: string;
      };
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            ok: true,
            code: "OK",
            message: "ok",
            durationMs: 42,
            fromCache: false,
            data: { status: "success" },
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json; charset=utf-8",
            },
          },
        ),
      ),
    );

    await expect(
      probeRuntime<{ status: string }>({
        kind: "unlock",
      }),
    ).resolves.toEqual({
      ok: true,
      code: "OK",
      message: "ok",
      durationMs: 42,
      fromCache: false,
      data: { status: "success" },
    });
  });
});
