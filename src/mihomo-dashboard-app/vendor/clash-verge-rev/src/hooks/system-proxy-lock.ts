import type { WebActionPolicy } from "@root/browser/runtime";

interface ResolveSystemProxyLockStateParams {
  policy: WebActionPolicy;
  tunEnabled: boolean;
  tunReason: string;
}

interface SystemProxyLockState {
  systemProxyDisabled: boolean;
  systemProxyDisabledReason: string;
}

export const resolveSystemProxyLockState = ({
  policy,
  tunEnabled,
  tunReason,
}: ResolveSystemProxyLockStateParams): SystemProxyLockState => {
  if (tunEnabled) {
    return {
      systemProxyDisabled: true,
      systemProxyDisabledReason: tunReason || policy.reason,
    };
  }

  if (policy.mode !== "enabled") {
    return {
      systemProxyDisabled: true,
      systemProxyDisabledReason: policy.reason,
    };
  }

  return {
    systemProxyDisabled: false,
    systemProxyDisabledReason: "",
  };
};
