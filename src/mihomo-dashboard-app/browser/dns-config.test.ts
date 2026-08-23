import { describe, expect, it } from "vitest";

import { assignOptionalDnsString, readOptionalDnsString } from "./dns-config";

describe("DNS optional field contract", () => {
  it("keeps optional fake-ip-range6 empty when absent and preserves values", () => {
    expect(readOptionalDnsString(undefined)).toBe("");
    expect(readOptionalDnsString({})).toBe("");
    expect(readOptionalDnsString("fdfe:dcba:9876::1/64")).toBe(
      "fdfe:dcba:9876::1/64",
    );

    const config: Record<string, unknown> = {};
    assignOptionalDnsString(config, "fake-ip-range6", "");
    expect(config).not.toHaveProperty("fake-ip-range6");
    assignOptionalDnsString(config, "fake-ip-range6", "fdfe:dcba:9876::1/64");
    expect(config["fake-ip-range6"]).toBe("fdfe:dcba:9876::1/64");
  });
});
