import { describe, expect, it } from "vitest";

import { buildTrayIconFileNames } from "./icon-paths";

describe("buildTrayIconFileNames", () => {
  it("uses timestamped filenames when update time exists", () => {
    expect(buildTrayIconFileNames("common", "123")).toEqual([
      "common-123.ico",
      "common-123.png",
    ]);
  });

  it("falls back to stable filenames when update time is empty", () => {
    expect(buildTrayIconFileNames("sysproxy")).toEqual([
      "sysproxy.ico",
      "sysproxy.png",
    ]);
  });
});
