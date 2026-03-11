export {};

import type {
  RuntimeContractWarning,
  RuntimeInfo,
} from "./runtime";

declare global {
  interface IConfigData {
    mixedPort?: number;
    socksPort?: number;
    redirPort?: number;
    tproxyPort?: number;
  }

  interface Window {
    __LZCAPP_MIHOMO__?: {
      secret?: string;
      // Deprecated: browser runtime now trusts the LazyCat login session.
      vergeApiSecret?: string;
      mihomoBaseUrl?: string;
      vergeApiBaseUrl?: string;
      appVersion?: string;
      runtimeInfo?: RuntimeInfo | null;
      runtimeWarning?: RuntimeContractWarning | null;
    };
    __VERGE_INITIAL_THEME_MODE?: "light" | "dark" | "system";
  }
}
