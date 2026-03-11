import { ChevronRightRounded } from "@mui/icons-material";
import {
  Box,
  type IconButtonProps,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListSubheader,
  Tooltip,
  type SvgIconProps,
} from "@mui/material";
import CircularProgress from "@mui/material/CircularProgress";
import React, { ReactNode, useState } from "react";

import { TooltipIcon } from "@/components/base";
import isAsyncFunction from "@/utils/is-async-function";

interface ItemProps {
  label: ReactNode;
  extra?: ReactNode;
  children?: ReactNode;
  secondary?: ReactNode;
  onClick?: () => void | Promise<any>;
  disabled?: boolean;
  disabledReason?: ReactNode;
}

export const SettingItem: React.FC<ItemProps> = ({
  label,
  extra,
  children,
  secondary,
  onClick,
  disabled = false,
  disabledReason,
}) => {
  const clickable = !!onClick;

  const primary = (
    <Box sx={{ display: "flex", alignItems: "center", fontSize: "14px" }}>
      <span>{label}</span>
      {extra ? extra : null}
    </Box>
  );

  const [isLoading, setIsLoading] = useState(false);
  const handleClick = () => {
    if (disabled) return;
    if (onClick) {
      if (isAsyncFunction(onClick)) {
        setIsLoading(true);
        onClick()!.finally(() => setIsLoading(false));
      } else {
        onClick();
      }
    }
  };

  return clickable ? (
    <ListItem disablePadding>
      <Tooltip
        title={disabled ? disabledReason ?? "" : ""}
        placement="top"
        disableHoverListener={!disabled || !disabledReason}
      >
        <span style={{ display: "block", width: "100%" }}>
          <ListItemButton onClick={handleClick} disabled={disabled || isLoading}>
            <ListItemText primary={primary} secondary={secondary} />
            {isLoading ? (
              <CircularProgress color="inherit" size={20} />
            ) : !disabled ? (
              <ChevronRightRounded />
            ) : null}
          </ListItemButton>
        </span>
      </Tooltip>
    </ListItem>
  ) : (
    <ListItem sx={{ pt: "5px", pb: "5px" }}>
      <ListItemText primary={primary} secondary={secondary} />
      {children}
    </ListItem>
  );
};

export const SettingList: React.FC<{
  title: string;
  children: ReactNode;
}> = ({ title, children }) => (
  <List>
    <ListSubheader
      sx={[
        { background: "transparent", fontSize: "16px", fontWeight: "700" },
        ({ palette }) => {
          return {
            color: palette.text.primary,
          };
        },
      ]}
      disableSticky
    >
      {title}
    </ListSubheader>

    {children}
  </List>
);

interface SettingExtraActionProps extends IconButtonProps {
  title?: string;
  icon?: React.ElementType<SvgIconProps>;
}

export const SettingExtraAction: React.FC<SettingExtraActionProps> = ({
  onClick,
  ...props
}) => (
  <Box
    sx={{ ml: 0.5, display: "inline-flex", alignItems: "center" }}
    onClick={(event) => event.stopPropagation()}
  >
    <TooltipIcon
      {...props}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.(event);
      }}
    />
  </Box>
);
