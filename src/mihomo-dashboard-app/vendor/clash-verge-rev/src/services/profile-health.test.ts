import { describe, expect, it } from "vitest";

import { getExpectedRuntimeInfo } from "../../../../browser/runtime";

import {
  getProfileHealth,
  hasUsableProxyProviderSnapshot,
  hasUsableProxySnapshot,
  shouldFreezeProxySnapshots,
  shouldRefreshAfterRecovery,
} from "./profile-health";

describe("profile health helpers", () => {
  it("freezes proxy snapshots while runtime profile health is degraded", () => {
    expect(
      shouldFreezeProxySnapshots({
        status: "degraded",
        activeProfileId: "demo",
        lastGoodProfileId: "demo",
        lastAppliedAt: "2026-03-31T01:44:24Z",
        lastError: "订阅拉取超时（20s）",
        providerCounts: { "high-premium": 7 },
      }),
    ).toBe(true);
  });

  it("requests a recovery refresh only when health turns ready again", () => {
    const degraded = {
      status: "degraded" as const,
      activeProfileId: "demo",
      lastGoodProfileId: "demo",
      lastAppliedAt: "2026-03-31T01:44:24Z",
      lastError: "订阅拉取超时（20s）",
      providerCounts: { "high-premium": 7 },
    };
    const ready = {
      ...degraded,
      status: "ready" as const,
      lastError: "",
    };

    expect(shouldRefreshAfterRecovery(degraded, ready)).toBe(true);
    expect(shouldRefreshAfterRecovery(ready, ready)).toBe(false);
  });

  it("treats proxy and provider snapshots as usable when shape is complete", () => {
    expect(
      hasUsableProxySnapshot({
        groups: [],
        proxies: [],
        global: { all: [] },
      }),
    ).toBe(true);
    expect(hasUsableProxyProviderSnapshot({ "high-premium": {} })).toBe(true);
    expect(hasUsableProxySnapshot(null)).toBe(false);
  });

  it("extracts optional profile health from runtime info", () => {
    const expected = getExpectedRuntimeInfo();
    const runtimeInfo = {
      ...expected,
      profileHealth: {
        status: "degraded" as const,
        activeProfileId: "demo",
        lastGoodProfileId: "demo",
        lastAppliedAt: "2026-03-31T01:44:24Z",
        lastError: "订阅拉取超时（20s）",
        providerCounts: { "high-premium": 7 },
      },
    };

    expect(getProfileHealth(runtimeInfo)?.status).toBe("degraded");
  });
});
