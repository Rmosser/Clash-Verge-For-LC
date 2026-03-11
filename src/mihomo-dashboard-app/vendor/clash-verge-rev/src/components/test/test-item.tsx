import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { LanguageRounded } from "@mui/icons-material";
import { Box, Divider, MenuItem, Menu, styled, alpha } from "@mui/material";
import { UnlistenFn } from "@tauri-apps/api/event";
import { useLockFn } from "ahooks";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { BaseLoading } from "@/components/base";
import { useIconCache } from "@/hooks/use-icon-cache";
import { useListen } from "@/hooks/use-listen";
import { cmdTestDelay } from "@/services/cmds";
import delayManager from "@/services/delay";
import { showNotice } from "@/services/notice-service";
import { debugLog } from "@/utils/debug";

import { TestBox } from "./test-box";

interface Props {
  id: string;
  itemData: IVergeTestItem;
  onEdit: () => void;
  onDelete: (uid: string) => void;
}

type ProbeDisplayState =
  | { type: "idle" }
  | { type: "loading" }
  | {
      type: "result";
      label: string;
      color?: string;
      message?: string;
    };

export const TestItem = ({
  id,
  itemData,
  onEdit,
  onDelete: removeTest,
}: Props) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id,
  });

  const { t } = useTranslation();
  const [anchorEl, setAnchorEl] = useState<any>(null);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const [probeState, setProbeState] = useState<ProbeDisplayState>({
    type: "idle",
  });
  const { uid, name, icon, url } = itemData;
  const iconCachePath = useIconCache({ icon, cacheKey: uid });
  const { addListener } = useListen();

  const onDelay = useCallback(async () => {
    setProbeState({ type: "loading" });

    try {
      const probe = await cmdTestDelay(url);
      const latencyMs = probe.data?.latencyMs;

      if (
        probe.data?.status === "success" &&
        typeof latencyMs === "number"
      ) {
        setProbeState({
          type: "result",
          label: delayManager.formatDelay(latencyMs),
          color: delayManager.formatDelayColor(latencyMs),
        });
        return;
      }

      setProbeState({
        type: "result",
        label: probe.code === "TIMEOUT" ? "Timeout" : "Failed",
        color: probe.code === "TIMEOUT" ? "warning.main" : "error.main",
        message: probe.data?.errorMessage || probe.message,
      });
    } catch (error) {
      setProbeState({
        type: "result",
        label: "Failed",
        color: "error.main",
        message: error instanceof Error ? error.message : "检测失败",
      });
    }
  }, [url]);

  const onEditTest = () => {
    setAnchorEl(null);
    onEdit();
  };

  const onDelete = useLockFn(async () => {
    setAnchorEl(null);
    try {
      removeTest(uid);
    } catch (err: any) {
      showNotice.error(err);
    }
  });

  const menu = [
    { label: "Edit", handler: onEditTest },
    { label: "Delete", handler: onDelete },
  ];

  useEffect(() => {
    let unlistenFn: UnlistenFn | null = null;

    const setupListener = async () => {
      if (unlistenFn) {
        unlistenFn();
      }
      unlistenFn = await addListener("verge://test-all", () => {
        onDelay();
      });
    };

    setupListener();

    return () => {
      if (unlistenFn) {
        debugLog(
          `TestItem for ${id} unmounting or url changed, cleaning up test-all listener.`,
        );
        unlistenFn();
      }
    };
  }, [url, addListener, onDelay, id]);

  return (
    <Box
      sx={{
        position: "relative",
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? "calc(infinity)" : undefined,
      }}
    >
      <TestBox
        onContextMenu={(event) => {
          const { clientX, clientY } = event;
          setPosition({ top: clientY, left: clientX });
          setAnchorEl(event.currentTarget);
          event.preventDefault();
        }}
      >
        <Box
          position="relative"
          sx={{ cursor: "move" }}
          ref={setNodeRef}
          {...attributes}
          {...listeners}
        >
          {icon && icon.trim() !== "" ? (
            <Box sx={{ display: "flex", justifyContent: "center" }}>
              {icon.trim().startsWith("http") && (
                <img
                  src={iconCachePath === "" ? icon : iconCachePath}
                  height="40px"
                />
              )}
              {icon.trim().startsWith("data") && (
                <img src={icon} height="40px" />
              )}
              {icon.trim().startsWith("<svg") && (
                <img
                  src={`data:image/svg+xml;base64,${btoa(icon)}`}
                  height="40px"
                />
              )}
            </Box>
          ) : (
            <Box sx={{ display: "flex", justifyContent: "center" }}>
              <LanguageRounded sx={{ height: "40px" }} fontSize="large" />
            </Box>
          )}

          <Box sx={{ display: "flex", justifyContent: "center" }}>{name}</Box>
        </Box>
        <Divider sx={{ marginTop: "8px" }} />
        <Box
          sx={{
            display: "flex",
            justifyContent: "center",
            marginTop: "8px",
            color: "primary.main",
          }}
        >
          {probeState.type === "loading" && (
            <Widget>
              <BaseLoading />
            </Widget>
          )}

          {probeState.type === "idle" && (
            <Widget
              className="the-check"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onDelay();
              }}
              sx={({ palette }) => ({
                ":hover": { bgcolor: alpha(palette.primary.main, 0.15) },
              })}
            >
              {t("tests.components.item.actions.test")}
            </Widget>
          )}

          {probeState.type === "result" && (
            <Widget
              className="the-delay"
              title={probeState.message || ""}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onDelay();
              }}
              color={probeState.color}
              sx={({ palette }) => ({
                ":hover": {
                  bgcolor: alpha(palette.primary.main, 0.15),
                },
              })}
            >
              {probeState.label}
            </Widget>
          )}
        </Box>
        {probeState.type === "result" && probeState.message && (
          <Box
            sx={{
              mt: 0.75,
              color: "text.secondary",
              fontSize: 12,
              lineHeight: 1.4,
              textAlign: "center",
            }}
          >
            {probeState.message}
          </Box>
        )}
      </TestBox>

      <Menu
        open={!!anchorEl}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorPosition={position}
        anchorReference="anchorPosition"
        transitionDuration={225}
        MenuListProps={{ sx: { py: 0.5 } }}
        onContextMenu={(e) => {
          setAnchorEl(null);
          e.preventDefault();
        }}
      >
        {menu.map((item) => (
          <MenuItem
            key={item.label}
            onClick={item.handler}
            sx={{ minWidth: 120 }}
            dense
          >
            {t(item.label)}
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );
};
const Widget = styled(Box)(({ theme: { typography } }) => ({
  padding: "3px 6px",
  fontSize: 14,
  fontFamily: typography.fontFamily,
  borderRadius: "4px",
}));
