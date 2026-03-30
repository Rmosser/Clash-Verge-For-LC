import { useLockFn } from "ahooks";
import { useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import useSWR, { mutate } from "swr";
import { closeAllConnections } from "tauri-plugin-mihomo-api";

import { resolveSystemProxyLockState } from "@/hooks/system-proxy-lock";
import { useVerge } from "@/hooks/use-verge";
import { useAppData } from "@/providers/app-data-context";
import { getAutotemProxy } from "@/services/cmds";
import { getWebActionPolicy } from "@root/browser/runtime";

// 系统代理状态检测统一逻辑
export const useSystemProxyState = () => {
  const { t } = useTranslation();
  const { verge, mutateVerge, patchVerge } = useVerge();
  const { sysproxy } = useAppData();
  const { data: autoproxy } = useSWR("getAutotemProxy", getAutotemProxy, {
    revalidateOnFocus: true,
    revalidateOnReconnect: true,
  });

  const { enable_system_proxy, proxy_auto_config, enable_tun_mode } = verge ?? {};
  const systemProxyPolicy = getWebActionPolicy("systemProxy");
  const { systemProxyDisabled, systemProxyDisabledReason } =
    resolveSystemProxyLockState({
      policy: systemProxyPolicy,
      tunEnabled: !!enable_tun_mode,
      tunReason: t("settings.sections.proxyControl.tooltips.tunMode"),
    });

  const getSystemProxyActualState = () => {
    const userEnabled = enable_system_proxy ?? false;

    // 用户配置状态应该与系统实际状态一致
    // 如果用户启用了系统代理，检查实际的系统状态
    if (userEnabled) {
      if (proxy_auto_config) {
        return autoproxy?.enable ?? false;
      } else {
        return sysproxy?.enable ?? false;
      }
    }

    // 用户没有启用时，返回 false
    return false;
  };

  const getSystemProxyIndicator = () => {
    if (proxy_auto_config) {
      return autoproxy?.enable ?? false;
    } else {
      return sysproxy?.enable ?? false;
    }
  };

  const updateProxyStatus = useCallback(async (isEnabling: boolean) => {
    // 关闭时更快响应，开启时等待系统确认
    const delay = isEnabling ? 20 : 10;
    await new Promise((resolve) => setTimeout(resolve, delay));
    await mutate("getSystemProxy");
    await mutate("getAutotemProxy");
  }, []);

  useEffect(() => {
    if (!enable_tun_mode || !enable_system_proxy) return;

    let cancelled = false;
    const disableSystemProxyForTun = async () => {
      mutateVerge({ ...verge, enable_system_proxy: false }, false);
      try {
        if (verge?.auto_close_connection) {
          await closeAllConnections();
        }
        await patchVerge({ enable_system_proxy: false });
        if (!cancelled) {
          await updateProxyStatus(false);
        }
      } catch (error) {
        console.warn(
          "[useSystemProxyState] failed to disable system proxy when TUN is enabled:",
          error,
        );
        if (!cancelled) {
          mutateVerge({ ...verge, enable_system_proxy: true }, false);
          await updateProxyStatus(true);
        }
      }
    };

    void disableSystemProxyForTun();

    return () => {
      cancelled = true;
    };
  }, [
    enable_tun_mode,
    enable_system_proxy,
    mutateVerge,
    patchVerge,
    updateProxyStatus,
    verge,
  ]);

  const toggleSystemProxy = useLockFn(async (enabled: boolean) => {
    if (systemProxyDisabled) {
      throw new Error(systemProxyDisabledReason || systemProxyPolicy.reason);
    }
    mutateVerge({ ...verge, enable_system_proxy: enabled }, false);

    try {
      if (!enabled && verge?.auto_close_connection) {
        await closeAllConnections();
      }
      await patchVerge({ enable_system_proxy: enabled });
      await updateProxyStatus(enabled);
    } catch (error) {
      console.warn("[useSystemProxyState] toggleSystemProxy failed:", error);
      mutateVerge({ ...verge, enable_system_proxy: !enabled }, false);
      await updateProxyStatus(!enabled);
      throw error;
    }
  });

  return {
    actualState: getSystemProxyActualState(),
    indicator: getSystemProxyIndicator(),
    configState: enable_system_proxy ?? false,
    sysproxy,
    autoproxy,
    proxy_auto_config,
    systemProxyDisabled,
    systemProxyDisabledReason,
    toggleSystemProxy,
  };
};
