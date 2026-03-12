import { describe, expect, it } from "vitest";

import {
  normalizeEpochToMs,
  normalizePlausibleEpochToMs,
} from "./normalize-epoch";

describe("normalizeEpochToMs", () => {
  it("normalizes seconds to milliseconds", () => {
    expect(normalizeEpochToMs(1_741_848_000)).toBe(1_741_848_000_000);
  });

  it("keeps millisecond timestamps unchanged", () => {
    expect(normalizeEpochToMs(1_741_848_000_000)).toBe(1_741_848_000_000);
  });
});

describe("normalizePlausibleEpochToMs", () => {
  it("keeps current-era timestamps", () => {
    expect(normalizePlausibleEpochToMs(1_741_848_000_000)).toBe(
      1_741_848_000_000,
    );
  });

  it("rejects implausibly large future timestamps", () => {
    expect(normalizePlausibleEpochToMs(1_741_848_000_000_000)).toBe(0);
  });
});
