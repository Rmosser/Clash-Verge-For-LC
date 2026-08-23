import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  healthcheckNodeInProvider,
  MihomoWebSocket,
  normalizeTraffic,
  upgradeCore,
} from "./tauri-plugin-mihomo-api";

type FakeHandler = (event: { data?: unknown }) => void;

class FakeWebSocket {
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readonly url: string;
  readyState = 0;
  private readonly handlers = new Map<string, Set<FakeHandler>>();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(
    eventName: string,
    handler: FakeHandler,
    _options?: { once?: boolean },
  ) {
    const handlers = this.handlers.get(eventName) ?? new Set<FakeHandler>();
    handlers.add(handler);
    this.handlers.set(eventName, handlers);
    if (eventName === "open") {
      queueMicrotask(() => {
        this.readyState = FakeWebSocket.OPEN;
        this.emit("open");
      });
    }
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.emit("close");
  }

  emit(eventName: string, event: { data?: unknown } = {}) {
    this.handlers.get(eventName)?.forEach((handler) => handler(event));
  }
}

const originalWindow = globalThis.window;
const originalWebSocket = globalThis.WebSocket;

beforeEach(() => {
  FakeWebSocket.instances = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { origin: "http://dashboard.test" },
      __LZCAPP_MIHOMO__: {
        mihomoBaseUrl: "/api",
        vergeApiBaseUrl: "/verge-api",
      },
    },
  });
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    value: FakeWebSocket,
  });
});

afterEach(() => {
  MihomoWebSocket.cleanupAll();
  vi.unstubAllGlobals();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: originalWindow,
  });
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    value: originalWebSocket,
  });
});

describe("WebPort Mihomo shim", () => {
  it("preserves complete traffic totals and fills missing totals with zero", () => {
    expect(normalizeTraffic({ up: 1, down: 2 })).toEqual({
      up: 1,
      down: 2,
      upTotal: 0,
      downTotal: 0,
    });
    expect(
      normalizeTraffic({ up: 1, down: 2, upTotal: 100, downTotal: 200 }),
    ).toEqual({ up: 1, down: 2, upTotal: 100, downTotal: 200 });
  });

  it("maps official uppercase log levels to controller query values", async () => {
    const socket = await MihomoWebSocket.connect_logs("WARNING");

    expect(FakeWebSocket.instances[0]?.url).toBe(
      "ws://dashboard.test/api/logs?level=warning",
    );
    await socket.close();
  });

  it("supports listener unsubscribe and cleanup for multiple sockets", async () => {
    const traffic = await MihomoWebSocket.connect_traffic();
    const memory = await MihomoWebSocket.connect_memory();
    const received: string[] = [];
    const unsubscribe = traffic.addListener((message) =>
      received.push(message.data),
    );

    FakeWebSocket.instances[0]?.emit("message", { data: "first" });
    unsubscribe();
    FakeWebSocket.instances[0]?.emit("message", { data: "ignored" });
    expect(received).toEqual(["first"]);

    MihomoWebSocket.cleanupAll();
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(
      FakeWebSocket.instances.every(
        (instance) => instance.readyState === FakeWebSocket.CLOSED,
      ),
    ).toBe(true);
    await memory.close();
  });

  it("routes provider delay and upgrade commands through the mock Verge API", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        if (body.cmd === "upgrade_core") {
          return new Response(JSON.stringify({ kind: "unsupported" }), {
            headers: { "content-type": "application/json" },
          });
        }
        return new Response(
          JSON.stringify({
            target: "node/1",
            status: "success",
            delay: 42,
          }),
          { headers: { "content-type": "application/json" } },
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      healthcheckNodeInProvider(
        "provider/a",
        "node/1",
        "https://probe.test",
        5000,
      ),
    ).resolves.toMatchObject({ status: "success", delay: 42 });
    await upgradeCore();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      cmd: "clash_api_get_provider_proxy_delay",
      args: {
        provider: "provider/a",
        name: "node/1",
        url: "https://probe.test",
        timeout: 5000,
      },
    });
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      cmd: "upgrade_core",
      args: {},
    });
    expect(
      fetchMock.mock.calls.every(([input]) => input === "/verge-api/invoke"),
    ).toBe(true);
  });
});
