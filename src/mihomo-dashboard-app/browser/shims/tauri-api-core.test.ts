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
});
