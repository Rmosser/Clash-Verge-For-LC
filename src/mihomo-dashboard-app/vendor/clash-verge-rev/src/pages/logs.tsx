import {
  PlayCircleOutlineRounded,
  PauseCircleOutlineRounded,
  SwapVertRounded,
} from "@mui/icons-material";
import { Alert, Box, Button, IconButton, MenuItem, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Virtuoso } from "react-virtuoso";

import {
  BaseEmpty,
  BaseLoading,
  BasePage,
  BaseSearchBox,
  BaseStyledSelect,
  type SearchState,
} from "@/components/base";
import LogItem from "@/components/log/log-item";
import { useClashLog } from "@/hooks/use-clash-log";
import { useLogData } from "@/hooks/use-log-data";

const LogPage = () => {
  const { t, i18n } = useTranslation();
  const [clashLog, setClashLog] = useClashLog();
  const enableLog = clashLog.enable;
  const logState = clashLog.logFilter;
  const logOrder = clashLog.logOrder ?? "asc";
  const isDescending = logOrder === "desc";

  const [match, setMatch] = useState(() => (_: string) => true);
  const [searchState, setSearchState] = useState<SearchState>();
  const {
    response: { data: logData },
    historyStatus,
    historyMessage,
    realtimeStatus,
    refreshGetClashLog,
  } = useLogData();

  const filterLogs = useMemo(() => {
    if (!logData || logData.length === 0) {
      return [];
    }

    // Server-side filtering handles level filtering via query parameters
    // We only need to apply search filtering here
    return logData.filter((data) => {
      // 构建完整的搜索文本，包含时间、类型和内容
      const searchText =
        `${data.time || ""} ${data.type} ${data.payload}`.toLowerCase();

      const matchesSearch = match(searchText);

      return (
        (logState == "all" ? true : data.type.includes(logState)) &&
        matchesSearch
      );
    });
  }, [logData, logState, match]);

  const filteredLogs = useMemo(
    () => (isDescending ? [...filterLogs].reverse() : filterLogs),
    [filterLogs, isDescending],
  );

  const logMessages = useMemo(
    () =>
      i18n.resolvedLanguage?.toLowerCase().startsWith("zh")
        ? {
            historyLoading: "正在加载历史日志...",
            historyFailed: "历史日志加载失败。",
            historyEmpty: "当前没有可显示的历史日志。",
            realtimeUnavailable:
              "实时日志不可用，当前已降级为仅显示历史日志。",
          }
        : {
            historyLoading: "Loading history logs...",
            historyFailed: "Failed to load history logs.",
            historyEmpty: "No history logs available.",
            realtimeUnavailable:
              "Realtime logs are unavailable. Showing history only.",
          },
    [i18n.resolvedLanguage],
  );

  const handleLogLevelChange = (newLevel: string) => {
    setClashLog((pre: any) => ({ ...pre, logFilter: newLevel }));
  };

  const handleToggleLog = async () => {
    setClashLog((pre: any) => ({ ...pre, enable: !enableLog }));
  };

  const handleToggleOrder = () => {
    setClashLog((pre: any) => ({
      ...pre,
      logOrder: pre.logOrder === "desc" ? "asc" : "desc",
    }));
  };

  const renderBody = () => {
    if (filteredLogs.length > 0) {
      return (
        <Virtuoso
          initialTopMostItemIndex={isDescending ? 0 : 999}
          data={filteredLogs}
          style={{
            flex: 1,
          }}
          itemContent={(index, item) => (
            <LogItem value={item} searchState={searchState} />
          )}
          followOutput={isDescending ? false : "smooth"}
        />
      );
    }

    if (historyStatus === "loading") {
      return (
        <Box
          sx={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 2,
            color: "text.secondary",
          }}
        >
          <BaseLoading />
          <Typography variant="body2">
            {logMessages.historyLoading}
          </Typography>
        </Box>
      );
    }

    if (historyStatus === "error") {
      return (
        <BaseEmpty
          text={logMessages.historyFailed}
          extra={
            historyMessage ? (
              <Typography
                variant="body2"
                sx={{ mt: 1, px: 2, textAlign: "center" }}
              >
                {historyMessage}
              </Typography>
            ) : undefined
          }
        />
      );
    }

    return <BaseEmpty text={logMessages.historyEmpty} />;
  };

  return (
    <BasePage
      full
      title={t("logs.page.title")}
      contentStyle={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "auto",
      }}
      header={
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <IconButton
            title={t(
              enableLog ? "shared.actions.pause" : "shared.actions.resume",
            )}
            aria-label={t(
              enableLog ? "shared.actions.pause" : "shared.actions.resume",
            )}
            size="small"
            color="inherit"
            onClick={handleToggleLog}
          >
            {enableLog ? (
              <PauseCircleOutlineRounded />
            ) : (
              <PlayCircleOutlineRounded />
            )}
          </IconButton>
          <IconButton
            title={t(
              isDescending
                ? "logs.actions.showAscending"
                : "logs.actions.showDescending",
            )}
            aria-label={t(
              isDescending
                ? "logs.actions.showAscending"
                : "logs.actions.showDescending",
            )}
            size="small"
            color="inherit"
            onClick={handleToggleOrder}
          >
            <SwapVertRounded
              sx={{
                transform: isDescending ? "scaleY(-1)" : "none",
                transition: "transform 0.2s ease",
              }}
            />
          </IconButton>

          <Button
            size="small"
            variant="contained"
            onClick={() => {
              refreshGetClashLog(true);
            }}
          >
            {t("shared.actions.clear")}
          </Button>
        </Box>
      }
    >
      <Box
        sx={{
          pt: 1,
          mb: 0.5,
          mx: "10px",
          height: "39px",
          display: "flex",
          alignItems: "center",
        }}
      >
        <BaseStyledSelect
          value={logState}
          onChange={(e) => handleLogLevelChange(e.target.value as LogFilter)}
        >
          <MenuItem value="all">{t("shared.filters.logLevels.all")}</MenuItem>
          <MenuItem value="debug">
            {t("shared.filters.logLevels.debug")}
          </MenuItem>
          <MenuItem value="info">{t("shared.filters.logLevels.info")}</MenuItem>
          <MenuItem value="warn">{t("shared.filters.logLevels.warn")}</MenuItem>
          <MenuItem value="err">{t("shared.filters.logLevels.error")}</MenuItem>
        </BaseStyledSelect>
        <BaseSearchBox
          onSearch={(matcher, state) => {
            setMatch(() => matcher);
            setSearchState(state);
          }}
        />
      </Box>
      {realtimeStatus === "degraded" && (
        <Alert severity="warning" sx={{ mx: 1.5, mb: 1 }}>
          {logMessages.realtimeUnavailable}
        </Alert>
      )}
      {historyStatus === "error" && filteredLogs.length > 0 && (
        <Alert severity="error" sx={{ mx: 1.5, mb: 1 }}>
          {historyMessage || logMessages.historyFailed}
        </Alert>
      )}
      {renderBody()}
    </BasePage>
  );
};

export default LogPage;
