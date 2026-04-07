import type { RuntimeInfo, RuntimeProfileHealth } from "@root/browser/runtime";

export const getProfileHealth = (
  runtimeInfo: RuntimeInfo | null | undefined,
): RuntimeProfileHealth | null => {
  const health = runtimeInfo?.profileHealth;
  if (!health) {
    return null;
  }
  return health;
};

export const shouldFreezeProxySnapshots = (
  health: RuntimeProfileHealth | null | undefined,
) => health?.status === "degraded";

export const shouldRefreshAfterRecovery = (
  previous: RuntimeProfileHealth | null | undefined,
  next: RuntimeProfileHealth | null | undefined,
) => previous?.status === "degraded" && next?.status === "ready";

export const hasUsableProxySnapshot = (value: unknown) => {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as {
    groups?: unknown[];
    proxies?: unknown[];
    global?: { all?: unknown[] } | null;
  };
  return (
    Array.isArray(candidate.groups) ||
    Array.isArray(candidate.proxies) ||
    !!candidate.global
  );
};

export const hasUsableProxyProviderSnapshot = (value: unknown) =>
  !!value && typeof value === "object";
