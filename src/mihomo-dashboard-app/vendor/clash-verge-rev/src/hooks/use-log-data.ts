import dayjs from "dayjs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { mutate } from "swr";
import { MihomoWebSocket, type LogLevel } from "tauri-plugin-mihomo-api";

import { getClashLogs } from "@/services/cmds";

import { useClashLog } from "./use-clash-log";
import { useMihomoWsSubscription } from "./use-mihomo-ws-subscription";

const MAX_LOG_NUM = 1000;
const FLUSH_DELAY_MS = 50;
const DEFAULT_REALTIME_DEGRADED_MESSAGE =
  "实时日志不可用，已降级为历史日志。";
const DEFAULT_HISTORY_ERROR_MESSAGE = "历史日志加载失败。";

type LogType = ILogItem["type"];

export type LogHistoryStatus = "idle" | "loading" | "ready" | "empty" | "error";
export type LogRealtimeStatus = "paused" | "connecting" | "ready" | "degraded";

const DEFAULT_LOG_TYPES: LogType[] = ["debug", "info", "warning", "error"];
const LOG_LEVEL_FILTERS: Record<LogLevel, LogType[]> = {
  debug: DEFAULT_LOG_TYPES,
  info: ["info", "warning", "error"],
  warning: ["warning", "error"],
  error: ["error"],
  silent: [],
};

const clampLogs = (logs: ILogItem[]): ILogItem[] =>
  logs.length > MAX_LOG_NUM ? logs.slice(-MAX_LOG_NUM) : logs;

const filterLogsByLevel = (
  logs: ILogItem[],
  allowedTypes: LogType[],
): ILogItem[] => {
  if (allowedTypes.length === 0) return [];
  if (allowedTypes.length === DEFAULT_LOG_TYPES.length) return logs;
  return logs.filter((log) => allowedTypes.includes(log.type));
};

const appendLogs = (
  current: ILogItem[] | undefined,
  incoming: ILogItem[],
): ILogItem[] => clampLogs([...(current ?? []), ...incoming]);

const mergeLogs = (historyLogs: ILogItem[], realtimeLogs: ILogItem[]) =>
  clampLogs([...historyLogs, ...realtimeLogs]);

export const useLogData = () => {
  const [clashLog] = useClashLog();
  const enableLog = clashLog.enable;
  const logLevel = clashLog.logLevel;
  const allowedTypes = LOG_LEVEL_FILTERS[logLevel] ?? DEFAULT_LOG_TYPES;

  const [historyLogs, setHistoryLogs] = useState<ILogItem[]>([]);
  const [historyStatus, setHistoryStatus] = useState<LogHistoryStatus>("idle");
  const [historyMessage, setHistoryMessage] = useState<string>();
  const [realtimeStatus, setRealtimeStatus] =
    useState<LogRealtimeStatus>("paused");
  const [realtimeMessage, setRealtimeMessage] = useState<string>();
  const [historyRefreshToken, setHistoryRefreshToken] = useState(0);

  const { response, refresh, subscriptionCacheKey } = useMihomoWsSubscription<
    ILogItem[]
  >({
    storageKey: "mihomo_logs_date",
    buildSubscriptKey: (date) => (enableLog ? `getClashLog-${date}` : null),
    fallbackData: [],
    keepPreviousData: true,
    connect: async () => {
      setRealtimeStatus("connecting");
      try {
        const socket = await MihomoWebSocket.connect_logs(logLevel);
        setRealtimeStatus("ready");
        setRealtimeMessage(undefined);
        return socket;
      } catch (error) {
        setRealtimeStatus("degraded");
        setRealtimeMessage(DEFAULT_REALTIME_DEGRADED_MESSAGE);
        throw error;
      }
    },
    setupHandlers: ({ next, scheduleReconnect, isMounted }) => {
      let flushTimer: ReturnType<typeof setTimeout> | null = null;
      const buffer: ILogItem[] = [];

      const clearFlushTimer = () => {
        if (flushTimer) {
          clearTimeout(flushTimer);
          flushTimer = null;
        }
      };

      const flush = () => {
        if (!buffer.length || !isMounted()) {
          flushTimer = null;
          return;
        }
        const pendingLogs = buffer.splice(0, buffer.length);
        next(null, (current) => appendLogs(current, pendingLogs));
        flushTimer = null;
      };

      return {
        handleMessage: (data) => {
          if (data.startsWith("Websocket error")) {
            setRealtimeStatus("degraded");
            setRealtimeMessage(DEFAULT_REALTIME_DEGRADED_MESSAGE);
            next(data);
            void scheduleReconnect();
            return;
          }

          try {
            const parsed = JSON.parse(data) as ILogItem;
            if (
              allowedTypes.length > 0 &&
              !allowedTypes.includes(parsed.type)
            ) {
              return;
            }
            parsed.time = dayjs().format("MM-DD HH:mm:ss");
            buffer.push(parsed);
            if (!flushTimer) {
              flushTimer = setTimeout(flush, FLUSH_DELAY_MS);
            }
          } catch (error) {
            next(error);
          }
        },
        cleanup: clearFlushTimer,
      };
    },
  });

  const previousLogLevelRef = useRef<string | undefined>(undefined);

  const filteredHistoryLogs = useMemo(
    () => clampLogs(filterLogsByLevel(historyLogs, allowedTypes)),
    [allowedTypes, historyLogs],
  );

  const filteredRealtimeLogs = useMemo(
    () => clampLogs(filterLogsByLevel(response.data ?? [], allowedTypes)),
    [allowedTypes, response.data],
  );

  const combinedLogs = useMemo(
    () => mergeLogs(filteredHistoryLogs, filteredRealtimeLogs),
    [filteredHistoryLogs, filteredRealtimeLogs],
  );

  const loadHistoryLogs = useCallback(async () => {
    setHistoryStatus("loading");
    setHistoryMessage(undefined);

    try {
      const logs = await getClashLogs();
      setHistoryLogs(logs);
      setHistoryStatus(logs.length > 0 ? "ready" : "empty");
    } catch (error) {
      setHistoryLogs([]);
      setHistoryStatus("error");
      setHistoryMessage(
        error instanceof Error && error.message
          ? error.message
          : DEFAULT_HISTORY_ERROR_MESSAGE,
      );
    }
  }, []);

  useEffect(() => {
    void loadHistoryLogs();
  }, [historyRefreshToken, loadHistoryLogs]);

  useEffect(() => {
    if (!enableLog) {
      setRealtimeStatus("paused");
      setRealtimeMessage(undefined);
      return;
    }

    setRealtimeStatus((current) =>
      current === "ready" ? current : "connecting",
    );
  }, [enableLog]);

  useEffect(() => {
    if (!logLevel) {
      previousLogLevelRef.current = logLevel ?? undefined;
      return;
    }

    if (previousLogLevelRef.current === logLevel) {
      return;
    }

    previousLogLevelRef.current = logLevel;
    if (enableLog) {
      setRealtimeStatus("connecting");
      refresh();
    }
  }, [enableLog, logLevel, refresh]);

  const refreshGetClashLog = (clear = false) => {
    if (clear) {
      setHistoryLogs([]);
      setHistoryStatus("empty");
      setHistoryMessage(undefined);
      setRealtimeMessage(undefined);
      if (subscriptionCacheKey) {
        mutate(subscriptionCacheKey, []);
      }
      return;
    }

    setHistoryRefreshToken((current) => current + 1);
    if (enableLog) {
      setRealtimeStatus("connecting");
      refresh();
    }
  };

  return {
    response: {
      ...response,
      data: combinedLogs,
    },
    historyStatus,
    historyMessage,
    realtimeStatus,
    realtimeMessage,
    refreshGetClashLog,
  };
};
