const RETRYABLE_IMPORT_ERROR_CODES = new Set([
  "PROFILE_FETCH_TIMEOUT",
  "PROFILE_FETCH_NETWORK_ERROR",
  "PROFILE_FETCH_HTTP_ERROR",
]);

const READY_IGNORE_PROXY_NAMES = new Set(["DIRECT", "REJECT"]);

export const shouldRetryImportWithSelfProxy = (code: string) =>
  RETRYABLE_IMPORT_ERROR_CODES.has(code);

export const resolveImportErrorNoticeKey = (
  code: string,
  isSameBoxSubHubLazycat: boolean,
) => {
  if (code === "PROFILE_HTML_LOGIN_PAGE") {
    return "profiles.page.feedback.notifications.importFailedHtmlLogin";
  }
  if (code === "PROFILE_CONTENT_INVALID") {
    return "profiles.page.feedback.notifications.importFailedInvalidContent";
  }
  if (code === "PROFILE_APPLY_FAILED") {
    return "profiles.page.feedback.notifications.importFailedApply";
  }
  if (code === "IMPORT_NODES_TIMEOUT") {
    return "profiles.page.feedback.notifications.importNodesTimeout";
  }
  if (code === "PROFILE_FETCH_TIMEOUT") {
    return isSameBoxSubHubLazycat
      ? "profiles.page.feedback.notifications.importSameBoxSubHubFail"
      : "profiles.page.feedback.notifications.importFailedTimeout";
  }
  if (code === "PROFILE_FETCH_NETWORK_ERROR") {
    return isSameBoxSubHubLazycat
      ? "profiles.page.feedback.notifications.importSameBoxSubHubFail"
      : "profiles.page.feedback.notifications.importFailedNetwork";
  }
  if (code === "PROFILE_FETCH_HTTP_ERROR") {
    return isSameBoxSubHubLazycat
      ? "profiles.page.feedback.notifications.importSameBoxSubHubFail"
      : "profiles.page.feedback.notifications.importFailedHttp";
  }
  return isSameBoxSubHubLazycat
    ? "profiles.page.feedback.notifications.importSameBoxSubHubFail"
    : "profiles.page.feedback.notifications.importFail";
};

export const hasReadyNodes = (
  proxyData: {
    proxies?: IProxyItem[];
  },
  providerRecord: Record<string, IProxyProviderItem>,
) => {
  const leafProxyCount = (proxyData?.proxies || []).filter((proxy) => {
    const name = String(proxy?.name || "").toUpperCase();
    return name && !READY_IGNORE_PROXY_NAMES.has(name);
  }).length;

  const providerProxyCount = Object.values(providerRecord || {}).reduce(
    (sum, provider) => sum + (provider?.proxies?.length || 0),
    0,
  );

  return leafProxyCount > 0 || providerProxyCount > 0;
};
