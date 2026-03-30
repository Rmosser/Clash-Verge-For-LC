import { describe, expect, it } from "vitest";

import { resolveSystemProxyLockState } from "./system-proxy-lock";

describe("resolveSystemProxyLockState", () => {
  it("disables system proxy with policy reason when policy is disabled and tun is off", () => {
    const result = resolveSystemProxyLockState({
      policy: { mode: "disabled", reason: "policy disabled" },
      tunEnabled: false,
      tunReason: "tun reason",
    });

    expect(result).toEqual({
      systemProxyDisabled: true,
      systemProxyDisabledReason: "policy disabled",
    });
  });

  it("disables system proxy with tun reason when policy is enabled and tun is on", () => {
    const result = resolveSystemProxyLockState({
      policy: { mode: "enabled", reason: "policy enabled" },
      tunEnabled: true,
      tunReason: "tun reason",
    });

    expect(result).toEqual({
      systemProxyDisabled: true,
      systemProxyDisabledReason: "tun reason",
    });
  });

  it("prioritizes tun reason over policy reason when both policy-disabled and tun-enabled", () => {
    const result = resolveSystemProxyLockState({
      policy: { mode: "disabled", reason: "policy disabled" },
      tunEnabled: true,
      tunReason: "tun reason",
    });

    expect(result).toEqual({
      systemProxyDisabled: true,
      systemProxyDisabledReason: "tun reason",
    });
  });
});
