import { describe, expect, it } from "vitest";

import {
  hasReadyNodes,
  resolveImportErrorNoticeKey,
  shouldRetryImportWithSelfProxy,
} from "../vendor/clash-verge-rev/src/pages/profiles-import";

describe("profiles import helpers", () => {
  it("marks timeout/http/network import failures as retryable", () => {
    expect(shouldRetryImportWithSelfProxy("PROFILE_FETCH_TIMEOUT")).toBe(true);
    expect(shouldRetryImportWithSelfProxy("PROFILE_FETCH_NETWORK_ERROR")).toBe(
      true,
    );
    expect(shouldRetryImportWithSelfProxy("PROFILE_FETCH_HTTP_ERROR")).toBe(
      true,
    );
    expect(shouldRetryImportWithSelfProxy("PROFILE_CONTENT_INVALID")).toBe(
      false,
    );
  });

  it("maps validation errors to explicit user-facing notices", () => {
    expect(
      resolveImportErrorNoticeKey("PROFILE_HTML_LOGIN_PAGE", false),
    ).toBe("profiles.page.feedback.notifications.importFailedHtmlLogin");
    expect(
      resolveImportErrorNoticeKey("PROFILE_CONTENT_INVALID", false),
    ).toBe("profiles.page.feedback.notifications.importFailedInvalidContent");
  });

  it("falls back to same-box guidance when configured", () => {
    expect(resolveImportErrorNoticeKey("PROFILE_FETCH_TIMEOUT", true)).toBe(
      "profiles.page.feedback.notifications.importSameBoxSubHubFail",
    );
  });

  it("detects ready nodes from either leaf proxies or providers", () => {
    expect(
      hasReadyNodes(
        {
          proxies: [
            { name: "DIRECT" } as IProxyItem,
            { name: "US-01" } as IProxyItem,
          ],
        },
        {},
      ),
    ).toBe(true);

    expect(
      hasReadyNodes(
        {
          proxies: [{ name: "DIRECT" } as IProxyItem],
        },
        {
          demo: {
            proxies: [{ name: "JP-01" } as IProxyItem],
          } as IProxyProviderItem,
        },
      ),
    ).toBe(true);

    expect(
      hasReadyNodes(
        {
          proxies: [
            { name: "DIRECT" } as IProxyItem,
            { name: "REJECT" } as IProxyItem,
          ],
        },
        {},
      ),
    ).toBe(false);
  });
});
