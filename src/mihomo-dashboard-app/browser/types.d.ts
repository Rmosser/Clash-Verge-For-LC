export {};

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
      vergeApiSecret?: string;
      mihomoBaseUrl?: string;
      vergeApiBaseUrl?: string;
      appVersion?: string;
    };
    __VERGE_INITIAL_THEME_MODE?: "light" | "dark" | "system";
  }
}
