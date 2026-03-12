import { afterEach, describe, expect, it, vi } from "vitest";

import {
  assessRuntimeContract,
  createWebCommandResult,
  getExpectedRuntimeInfo,
  getWebActionPolicy,
} from "../../../../browser/runtime";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getWebActionPolicy", () => {
  it("marks directory open as degraded with copy-path fallback", () => {
    expect(getWebActionPolicy("directoryOpen")).toEqual({
      mode: "degraded",
      reason: "LazyCat Web 版无法直接打开宿主机目录，将改为复制目录路径。",
      label: "复制路径",
      fallback: "copy-path",
    });
  });

  it("marks devtools as disabled with browser guidance", () => {
    expect(getWebActionPolicy("devtools")).toEqual({
      mode: "disabled",
      reason: "请使用浏览器 DevTools。",
      label: "浏览器 DevTools",
    });
  });

  it("prefers runtime capability overrides when the backend reports empty runtime mode", () => {
    const expected = getExpectedRuntimeInfo();
    vi.stubGlobal("window", {
      __LZCAPP_MIHOMO__: {
        runtimeInfo: {
          ...expected,
          capabilities: {
            ...expected.capabilities,
            runtimeProfile: {
              mode: "degraded",
              reason:
                "当前没有活动配置文件；运行态修改会写入空配置运行态，需要持久配置时请先新建或选择配置。",
              label: "空配置运行态",
            },
          },
        },
      },
    } as typeof globalThis & {
      __LZCAPP_MIHOMO__?: {
        runtimeInfo?: typeof expected;
      };
    });

    expect(getWebActionPolicy("runtimeProfile")).toEqual({
      mode: "degraded",
      reason:
        "当前没有活动配置文件；运行态修改会写入空配置运行态，需要持久配置时请先新建或选择配置。",
      label: "空配置运行态",
    });
  });
});

describe("createWebCommandResult", () => {
  it("preserves kind, message and data payload", () => {
    expect(
      createWebCommandResult("degraded", "copied", { path: "/tmp/demo" }),
    ).toEqual({
      kind: "degraded",
      message: "copied",
      data: { path: "/tmp/demo" },
    });
  });
});

describe("assessRuntimeContract", () => {
  it("blocks startup when package fingerprint mismatches", () => {
    const expected = getExpectedRuntimeInfo();
    expect(
      assessRuntimeContract({
        ...expected,
        packageFingerprint: `${expected.packageFingerprint}-drift`,
      }).status,
    ).toBe("blocked");
  });

  it("warns on build drift when contract is still compatible", () => {
    const expected = getExpectedRuntimeInfo();
    const assessment = assessRuntimeContract({
      ...expected,
      buildId: `${expected.buildId}-next`,
      gitCommit: "deadbeef",
    });

    expect(assessment.status).toBe("warning");
    expect(assessment.warning?.code).toBe("DEPLOYMENT_DRIFT");
  });
});
