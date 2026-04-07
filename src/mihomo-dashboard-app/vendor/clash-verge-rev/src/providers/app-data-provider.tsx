import { listen } from "@tauri-apps/api/event";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import {
  getBaseConfig,
  getRuleProviders,
  getRules,
} from "tauri-plugin-mihomo-api";
import { vergeJson, type RuntimeInfo } from "@root/browser/runtime";

import { useVerge } from "@/hooks/use-verge";
import {
  calcuProxies,
  calcuProxyProviders,
  getAppUptime,
  getRunningMode,
  getSystemProxy,
} from "@/services/cmds";
import { SWR_DEFAULTS, SWR_MIHOMO } from "@/services/config";
import {
  getProfileHealth,
  hasUsableProxyProviderSnapshot,
  hasUsableProxySnapshot,
  shouldFreezeProxySnapshots,
  shouldRefreshAfterRecovery,
} from "@/services/profile-health";

import { AppDataContext, AppDataContextType } from "./app-data-context";

// 全局数据提供者组件
export const AppDataProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { verge } = useVerge();

  const { data: proxiesData, mutate: refreshProxy } = useSWR(
    "getProxies",
    calcuProxies,
    SWR_MIHOMO,
  );

  const { data: clashConfig, mutate: refreshClashConfig } = useSWR(
    "getClashConfig",
    getBaseConfig,
    SWR_MIHOMO,
  );

  const { data: proxyProviders, mutate: refreshProxyProviders } = useSWR(
    "getProxyProviders",
    calcuProxyProviders,
    SWR_MIHOMO,
  );

  const { data: runtimeInfo, mutate: refreshRuntimeInfo } = useSWR(
    "getRuntimeInfo",
    () => vergeJson<RuntimeInfo>("/runtime-info"),
    {
      ...SWR_DEFAULTS,
      refreshInterval: 5000,
      errorRetryCount: 1,
    },
  );

  const { data: ruleProviders, mutate: refreshRuleProviders } = useSWR(
    "getRuleProviders",
    getRuleProviders,
    SWR_MIHOMO,
  );

  const { data: rulesData, mutate: refreshRules } = useSWR(
    "getRules",
    getRules,
    SWR_MIHOMO,
  );

  useEffect(() => {
    let lastProfileId: string | null = null;
    let lastUpdateTime = 0;
    const refreshThrottle = 800;

    let isUnmounted = false;
    const scheduledTimeouts = new Set<number>();
    const cleanupFns: Array<() => void> = [];

    const registerCleanup = (fn: () => void) => {
      if (isUnmounted) {
        try {
          fn();
        } catch (error) {
          console.error("[DataProvider] Immediate cleanup failed:", error);
        }
      } else {
        cleanupFns.push(fn);
      }
    };

    const addWindowListener = (eventName: string, handler: EventListener) => {
      // eslint-disable-next-line @eslint-react/web-api/no-leaked-event-listener
      window.addEventListener(eventName, handler);
      return () => window.removeEventListener(eventName, handler);
    };

    const scheduleTimeout = (
      callback: () => void | Promise<void>,
      delay: number,
    ) => {
      if (isUnmounted) return -1;

      const timeoutId = window.setTimeout(() => {
        scheduledTimeouts.delete(timeoutId);
        if (!isUnmounted) {
          void callback();
        }
      }, delay);

      scheduledTimeouts.add(timeoutId);
      return timeoutId;
    };

    const clearAllTimeouts = () => {
      scheduledTimeouts.forEach((timeoutId) => clearTimeout(timeoutId));
      scheduledTimeouts.clear();
    };

    const handleProfileChanged = (event: { payload: string }) => {
      const newProfileId = event.payload;
      const now = Date.now();

      if (
        lastProfileId === newProfileId &&
        now - lastUpdateTime < refreshThrottle
      ) {
        return;
      }

      lastProfileId = newProfileId;
      lastUpdateTime = now;

      scheduleTimeout(() => {
        refreshRules().catch((error) =>
          console.warn("[DataProvider] Rules refresh failed:", error),
        );
        refreshRuleProviders().catch((error) =>
          console.warn("[DataProvider] Rule providers refresh failed:", error),
        );
      }, 200);
    };

    const handleRefreshClash = () => {
      const now = Date.now();
      if (now - lastUpdateTime <= refreshThrottle) return;

      lastUpdateTime = now;
      scheduleTimeout(async () => {
        await Promise.all([
          refreshProxy().catch((error) =>
            console.error("[DataProvider] Proxy refresh failed:", error),
          ),
          refreshClashConfig().catch((error) =>
            console.error("[DataProvider] Clash config refresh failed:", error),
          ),
        ]);
      }, 200);
    };

    const handleRefreshProxy = () => {
      const now = Date.now();
      if (now - lastUpdateTime <= refreshThrottle) return;

      lastUpdateTime = now;
      scheduleTimeout(() => {
        refreshProxy().catch((error) =>
          console.warn("[DataProvider] Proxy refresh failed:", error),
        );
      }, 200);
    };

    const initializeListeners = async () => {
      try {
        const unlistenProfile = await listen<string>(
          "profile-changed",
          handleProfileChanged,
        );
        registerCleanup(unlistenProfile);
      } catch (error) {
        console.error("[AppDataProvider] 监听 Profile 事件失败:", error);
      }

      try {
        const unlistenClash = await listen(
          "verge://refresh-clash-config",
          handleRefreshClash,
        );
        const unlistenProxy = await listen(
          "verge://refresh-proxy-config",
          handleRefreshProxy,
        );

        registerCleanup(() => {
          unlistenClash();
          unlistenProxy();
        });
      } catch (error) {
        console.warn("[AppDataProvider] 设置 Tauri 事件监听器失败:", error);

        const fallbackHandlers: Array<[string, EventListener]> = [
          ["verge://refresh-clash-config", handleRefreshClash],
          ["verge://refresh-proxy-config", handleRefreshProxy],
        ];

        fallbackHandlers.forEach(([eventName, handler]) => {
          registerCleanup(addWindowListener(eventName, handler));
        });
      }
    };

    void initializeListeners();

    return () => {
      isUnmounted = true;
      clearAllTimeouts();

      const errors: Error[] = [];
      cleanupFns.splice(0).forEach((fn) => {
        try {
          fn();
        } catch (error) {
          errors.push(
            error instanceof Error ? error : new Error(String(error)),
          );
        }
      });

      if (errors.length > 0) {
        console.error(
          `[DataProvider] ${errors.length} errors during cleanup:`,
          errors,
        );
      }
    };
  }, [refreshProxy, refreshClashConfig, refreshRules, refreshRuleProviders]);

  const { data: sysproxy, mutate: refreshSysproxy } = useSWR(
    "getSystemProxy",
    getSystemProxy,
    SWR_DEFAULTS,
  );

  const { data: runningMode } = useSWR(
    "getRunningMode",
    getRunningMode,
    SWR_DEFAULTS,
  );

  const { data: uptimeData } = useSWR("appUptime", getAppUptime, {
    ...SWR_DEFAULTS,
    refreshInterval: 3000,
    errorRetryCount: 1,
  });

  const profileHealth = getProfileHealth(runtimeInfo);
  const [stableProxiesData, setStableProxiesData] = useState<any>(null);
  const [stableProxyProviders, setStableProxyProviders] = useState<
    Record<string, unknown> | null
  >(null);
  const previousProfileHealthRef = useRef(profileHealth);

  useEffect(() => {
    if (!shouldFreezeProxySnapshots(profileHealth) && hasUsableProxySnapshot(proxiesData)) {
      setStableProxiesData(proxiesData);
    }
  }, [profileHealth, proxiesData]);

  useEffect(() => {
    if (
      !shouldFreezeProxySnapshots(profileHealth) &&
      hasUsableProxyProviderSnapshot(proxyProviders)
    ) {
      setStableProxyProviders(proxyProviders);
    }
  }, [profileHealth, proxyProviders]);

  useEffect(() => {
    const previous = previousProfileHealthRef.current;
    if (shouldRefreshAfterRecovery(previous, profileHealth)) {
      void Promise.allSettled([
        refreshProxy(),
        refreshProxyProviders(),
        refreshRuntimeInfo(),
      ]);
    }
    previousProfileHealthRef.current = profileHealth;
  }, [profileHealth, refreshProxy, refreshProxyProviders, refreshRuntimeInfo]);

  const effectiveProxiesData =
    shouldFreezeProxySnapshots(profileHealth) && stableProxiesData
      ? stableProxiesData
      : (proxiesData ?? stableProxiesData);
  const effectiveProxyProviders =
    shouldFreezeProxySnapshots(profileHealth) && stableProxyProviders
      ? stableProxyProviders
      : (proxyProviders ?? stableProxyProviders ?? {});
  const staleProxyData =
    shouldFreezeProxySnapshots(profileHealth) && !!stableProxiesData;

  // 提供统一的刷新方法
  const refreshAll = useCallback(async () => {
    await Promise.all([
      refreshProxy(),
      refreshClashConfig(),
      refreshRules(),
      refreshSysproxy(),
      refreshProxyProviders(),
      refreshRuleProviders(),
      refreshRuntimeInfo(),
    ]);
  }, [
    refreshProxy,
    refreshClashConfig,
    refreshRules,
    refreshSysproxy,
    refreshProxyProviders,
    refreshRuleProviders,
    refreshRuntimeInfo,
  ]);

  // 聚合所有数据
  const value = useMemo(() => {
    // 计算系统代理地址
    const calculateSystemProxyAddress = () => {
      if (!verge || !clashConfig) return "-";

      const isPacMode = verge.proxy_auto_config ?? false;

      if (isPacMode) {
        // PAC模式：显示我们期望设置的代理地址
        const proxyHost = verge.proxy_host || "127.0.0.1";
        const proxyPort =
          verge.verge_mixed_port || clashConfig.mixedPort || 7897;
        return `${proxyHost}:${proxyPort}`;
      } else {
        // HTTP代理模式：优先使用系统地址，但如果格式不正确则使用期望地址
        const systemServer = sysproxy?.server;
        if (
          systemServer &&
          systemServer !== "-" &&
          !systemServer.startsWith(":")
        ) {
          return systemServer;
        } else {
          // 系统地址无效，返回期望的代理地址
          const proxyHost = verge.proxy_host || "127.0.0.1";
          const proxyPort =
            verge.verge_mixed_port || clashConfig.mixedPort || 7897;
          return `${proxyHost}:${proxyPort}`;
        }
      }
    };

    return {
      // 数据
      proxies: effectiveProxiesData,
      clashConfig,
      rules: rulesData?.rules ?? [],
      sysproxy,
      runningMode,
      uptime: uptimeData || 0,

      // 提供者数据
      proxyProviders: effectiveProxyProviders as AppDataContextType["proxyProviders"],
      ruleProviders: ruleProviders?.providers || {},
      runtimeInfo: runtimeInfo || null,
      profileHealth,
      staleProxyData,

      systemProxyAddress: calculateSystemProxyAddress(),

      // 刷新方法
      refreshProxy,
      refreshClashConfig,
      refreshRules,
      refreshSysproxy,
      refreshProxyProviders,
      refreshRuleProviders,
      refreshAll,
    } as AppDataContextType;
  }, [
    proxiesData,
    effectiveProxiesData,
    clashConfig,
    rulesData,
    sysproxy,
    runningMode,
    uptimeData,
    proxyProviders,
    effectiveProxyProviders,
    ruleProviders,
    runtimeInfo,
    profileHealth,
    staleProxyData,
    verge,
    refreshProxy,
    refreshClashConfig,
    refreshRules,
    refreshSysproxy,
    refreshProxyProviders,
    refreshRuleProviders,
    refreshRuntimeInfo,
    refreshAll,
  ]);

  return <AppDataContext value={value}>{children}</AppDataContext>;
};
