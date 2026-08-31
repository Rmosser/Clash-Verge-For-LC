import { beforeEach, describe, expect, it, vi } from "vitest";

const { vergeInvokeMock } = vi.hoisted(() => ({
  vergeInvokeMock: vi.fn(),
}));

vi.mock("../runtime", () => ({
  basename: (value: string) => value,
  createWebCommandResult: vi.fn(),
  dispatchAppEvent: vi.fn(),
  getRegisteredFile: vi.fn(),
  getLzcConfig: vi.fn(),
  getUnsupportedWebFeatureMessage: vi.fn(),
  getWebActionPolicy: vi.fn(),
  isLzcWebRuntime: vi.fn(() => false),
  isWebCommandResult: vi.fn(() => false),
  resolveAppFileUrl: vi.fn(),
  saveBlob: vi.fn(),
  textToBase64: vi.fn(),
  vergeInvoke: vergeInvokeMock,
}));

import { invoke } from "./tauri-api-core";
import {
  normalizeSystemInfo,
  normalizeTestDelay,
} from "./web-command-contracts";

const emptySystemInfo = {
  system_name: "",
  system_version: "",
  system_kernel_version: "",
  system_arch: "",
  app_version: "",
  app_core_mode: "",
  app_is_admin: false,
};

describe("WebPort command boundary", () => {
  beforeEach(() => {
    vergeInvokeMock.mockReset();
  });

  it("normalizes legacy DNS validation tuples into valid and invalid outcomes", async () => {
    vergeInvokeMock.mockResolvedValueOnce([true, "ok"]);
    await expect(invoke("validate_dns_config", {})).resolves.toEqual({
      status: "valid",
    });

    vergeInvokeMock.mockResolvedValueOnce([false, "invalid config"]);
    await expect(invoke("validate_dns_config", {})).resolves.toEqual({
      status: "invalid",
      kind: "config",
      message: "invalid config",
    });
  });

  it("normalizes the WebPort delay object into the vendored numeric contract", async () => {
    vergeInvokeMock.mockResolvedValueOnce({
      target: "https://probe.test",
      status: "success",
      latencyMs: 42,
      errorCode: null,
      errorMessage: null,
    });

    await expect(
      invoke<number>("test_delay", { url: "https://probe.test" }),
    ).resolves.toBe(42);

    vergeInvokeMock.mockResolvedValueOnce({
      target: "https://probe.test",
      status: "timeout",
      errorCode: "TIMEOUT",
      errorMessage: "检测超时",
    });
    await expect(
      invoke<number>("test_delay", { url: "https://probe.test" }),
    ).resolves.toBe(0);

    vergeInvokeMock.mockResolvedValueOnce({
      target: "https://probe.test",
      status: "failed",
      errorCode: "PROXY_UNREACHABLE",
      errorMessage: "当前代理链路不可达",
    });
    await expect(
      invoke<number>("test_delay", { url: "https://probe.test" }),
    ).resolves.toBe(1_000_000);

    vergeInvokeMock.mockResolvedValueOnce({
      target: "https://probe.test",
      status: "network_error",
    });
    await expect(
      invoke<number>("test_delay", { url: "https://probe.test" }),
    ).resolves.toBe(1_000_000);

    vergeInvokeMock.mockResolvedValueOnce(null);
    await expect(
      invoke<number>("test_delay", { url: "https://probe.test" }),
    ).resolves.toBe(-1);
  });

  it("normalizes the WebPort system-info text into all fields consumed by the vendored UI", async () => {
    vergeInvokeMock.mockResolvedValueOnce(
      "System Name: Debian GNU/Linux\nSystem Version: 12 (bookworm)\nKernel Version: 6.1.0",
    );

    await expect(invoke("get_system_info")).resolves.toEqual({
      system_name: "Debian GNU/Linux",
      system_version: "12 (bookworm)",
      system_kernel_version: "6.1.0",
      system_arch: "",
      app_version: "",
      app_core_mode: "",
      app_is_admin: false,
    });

    vergeInvokeMock.mockResolvedValueOnce("");
    await expect(invoke("get_system_info")).resolves.toEqual(emptySystemInfo);

    vergeInvokeMock.mockResolvedValueOnce({
      errorCode: "SYSTEM_INFO_UNAVAILABLE",
    });
    await expect(invoke("get_system_info")).resolves.toEqual(emptySystemInfo);

    expect(normalizeSystemInfo(null)).toEqual(emptySystemInfo);
  });

  it("rejects non-finite and non-structured delay payloads without rendering a fake latency", () => {
    expect(normalizeTestDelay({ status: "success", latencyMs: NaN })).toBe(-1);
    expect(normalizeTestDelay({ status: "success", latencyMs: Infinity })).toBe(
      -1,
    );
    expect(normalizeTestDelay({ status: "success" })).toBe(-1);
    expect(normalizeTestDelay({ status: "failed", latencyMs: "42" })).toBe(-1);
    expect(
      normalizeTestDelay({ status: "target_unreachable", latencyMs: 42 }),
    ).toBe(1_000_000);
    expect(normalizeTestDelay({ status: "future_status", latencyMs: 42 })).toBe(
      -1,
    );
    expect(normalizeTestDelay([])).toBe(-1);
  });
});
