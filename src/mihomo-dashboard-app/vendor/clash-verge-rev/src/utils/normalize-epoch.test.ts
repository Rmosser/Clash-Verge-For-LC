import { describe, expect, it } from "vitest";

import { normalizeEpochToMs } from "./normalize-epoch";

describe("normalizeEpochToMs", () => {
  it("converts epoch seconds into milliseconds", () => {
    expect(normalizeEpochToMs(1773287839)).toBe(1773287839000);
  });

  it("preserves epoch milliseconds", () => {
    expect(normalizeEpochToMs(1773287839852)).toBe(1773287839852);
  });

  it("returns 0 for invalid values", () => {
    expect(normalizeEpochToMs()).toBe(0);
    expect(normalizeEpochToMs(0)).toBe(0);
    expect(normalizeEpochToMs(Number.NaN)).toBe(0);
  });
});
