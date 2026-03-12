import dayjs from "dayjs";

const MIHOMO_JOURNAL_LINE =
  /^time="(.+?)"\s+level=(debug|info|warning|warn|error|err)\s+msg="([\s\S]*?)"$/i;

const LEVEL_ALIAS: Record<string, ILogItem["type"]> = {
  debug: "debug",
  info: "info",
  warning: "warning",
  warn: "warning",
  error: "error",
  err: "error",
};

export const parseClashLogLine = (line: string): ILogItem | null => {
  const trimmed = String(line || "").trim();
  if (!trimmed) return null;

  const match = trimmed.match(MIHOMO_JOURNAL_LINE);
  if (!match) return null;

  const [, rawTime, rawLevel, payload] = match;
  const type = LEVEL_ALIAS[rawLevel.toLowerCase()];
  const parsedTime = dayjs(rawTime);

  if (!type || !parsedTime.isValid()) {
    return null;
  }

  return {
    time: parsedTime.format("MM-DD HH:mm:ss"),
    type,
    payload,
  };
};

export const parseClashLogLines = (lines: string[]): ILogItem[] =>
  lines.reduce<ILogItem[]>((acc, line) => {
    const parsed = parseClashLogLine(line);
    if (parsed) {
      acc.push(parsed);
    }
    return acc;
  }, []);
