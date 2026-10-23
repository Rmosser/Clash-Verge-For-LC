import { describe, expect, it } from "vitest";

import { buildProxyView } from "./proxy-view";

describe("Web proxy view", () => {
  const proxies = {
    G: { type: "Selector", all: ["same", "same"] },
    DIRECT: { type: "Direct" },
  };
  const providers = {
    A: { vehicleType: "HTTP", proxies: [{ name: "same", type: "ss" }] },
    B: { vehicleType: "HTTP", proxies: [{ name: "same", type: "ss" }] },
  };
  it("binds same-name occurrences to ordered provider sources", () => {
    const view = buildProxyView(proxies, providers, {
      "proxy-groups": [{ name: "G", use: ["B", "A"] }],
    });
    const members = view.groups[0].members;
    expect(
      members.map((m) => m.kind === "node" && view.records[m.recordId].source),
    ).toEqual([
      { kind: "provider", providerName: "B", proxyName: "same" },
      { kind: "provider", providerName: "A", proxyName: "same" },
    ]);
  });
  it("keeps ambiguous and unavailable providers explicit", () => {
    expect(buildProxyView(proxies, providers, {}).groups[0].members[0]).toEqual(
      { kind: "unresolved", name: "same", reason: "ambiguous" },
    );
    expect(buildProxyView(proxies, null, {}).groups[0].members[0]).toEqual({
      kind: "unresolved",
      name: "same",
      reason: "provider-unavailable",
    });
  });
});
