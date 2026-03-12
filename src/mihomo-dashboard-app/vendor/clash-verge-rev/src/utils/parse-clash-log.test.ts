import { describe, expect, it } from "vitest";

import { parseClashLogLine, parseClashLogLines } from "./parse-clash-log";

describe("parseClashLogLine", () => {
  it("parses Mihomo journal lines into ILogItem", () => {
    expect(
      parseClashLogLine(
        'time="2026-03-12T15:16:32.190504926+08:00" level=info msg="Start initial configuration in progress"',
      ),
    ).toEqual({
      time: "03-12 15:16:32",
      type: "info",
      payload: "Start initial configuration in progress",
    });
  });

  it("normalizes warn and err levels", () => {
    expect(
      parseClashLogLine(
        'time="2026-03-12T15:16:32.190504926+08:00" level=warn msg="warn line"',
      ),
    )?.toMatchObject({ type: "warning" });
    expect(
      parseClashLogLine(
        'time="2026-03-12T15:16:32.190504926+08:00" level=err msg="err line"',
      ),
    )?.toMatchObject({ type: "error" });
  });

  it("ignores systemd and malformed lines", () => {
    expect(
      parseClashLogLine(
        "Started mihomo.service - Mihomo (Clash Meta).",
      ),
    ).toBeNull();
    expect(parseClashLogLine("")).toBeNull();
    expect(parseClashLogLine("not a clash log")).toBeNull();
  });
});

describe("parseClashLogLines", () => {
  it("keeps only parseable Mihomo lines", () => {
    expect(
      parseClashLogLines([
        'time="2026-03-12T15:16:32.190504926+08:00" level=info msg="line 1"',
        "Started mihomo.service - Mihomo (Clash Meta).",
        'time="2026-03-12T15:16:33.190504926+08:00" level=warning msg="line 2"',
      ]),
    ).toEqual([
      {
        time: "03-12 15:16:32",
        type: "info",
        payload: "line 1",
      },
      {
        time: "03-12 15:16:33",
        type: "warning",
        payload: "line 2",
      },
    ]);
  });
});
