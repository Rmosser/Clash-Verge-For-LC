/// <reference types="vite/client" />
/// <reference types="vite-plugin-svgr/client" />
import "./assets/styles/index.scss";
import "./utils/monaco";

import { ResizeObserver } from "@juggle/resize-observer";
import { ComposeContextProvider } from "foxact/compose-context-provider";
import React from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { MihomoWebSocket } from "tauri-plugin-mihomo-api";

import {
  assessRuntimeContract,
  getRuntimeInfo,
  persistRuntimeAssessment,
  type RuntimeContractAssessment,
} from "../../../browser/runtime";
import { BaseErrorBoundary } from "./components/base";
import { router } from "./pages/_routers";
import { AppDataProvider } from "./providers/app-data-provider";
import { WindowProvider } from "./providers/window";
import { FALLBACK_LANGUAGE, initializeLanguage } from "./services/i18n";
import {
  preloadAppData,
  resolveThemeMode,
  getPreloadConfig,
} from "./services/preload";
import {
  LoadingCacheProvider,
  ThemeModeProvider,
  UpdateStateProvider,
} from "./services/states";
import { disableWebViewShortcuts } from "./utils/disable-webview-shortcuts";
import {
  isIgnoredMonacoWorkerError,
  patchMonacoWorkerConsole,
} from "./utils/monaco-worker-ignore";

if (!window.ResizeObserver) {
  window.ResizeObserver = ResizeObserver;
}

const mainElementId = "root";
const container = document.getElementById(mainElementId);

if (!container) {
  throw new Error(
    `No container '${mainElementId}' found to render application`,
  );
}

disableWebViewShortcuts();

const initializeApp = (initialThemeMode: "light" | "dark") => {
  const contexts = [
    <ThemeModeProvider key="theme" initialState={initialThemeMode} />,
    <LoadingCacheProvider key="loading" />,
    <UpdateStateProvider key="update" />,
  ];

  const root = createRoot(container);
  root.render(
    <React.StrictMode>
      <ComposeContextProvider contexts={contexts}>
        <BaseErrorBoundary>
          <WindowProvider>
            <AppDataProvider>
              <RouterProvider router={router} />
            </AppDataProvider>
          </WindowProvider>
        </BaseErrorBoundary>
      </ComposeContextProvider>
    </React.StrictMode>,
  );
};

const renderRuntimeBlocked = (assessment: RuntimeContractAssessment) => {
  const root = createRoot(container);
  const actual = assessment.actual;

  root.render(
    <React.StrictMode>
      <div
        style={{
          minHeight: "100vh",
          background: "linear-gradient(180deg, #f6f7fb 0%, #edf1f7 100%)",
          color: "#172033",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
          fontFamily:
            '"Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif',
        }}
      >
        <div
          style={{
            width: "min(720px, 100%)",
            background: "rgba(255,255,255,0.94)",
            border: "1px solid rgba(23,32,51,0.08)",
            borderRadius: "20px",
            boxShadow: "0 18px 50px rgba(17, 24, 39, 0.12)",
            padding: "28px 32px",
          }}
        >
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "#7a8699",
              marginBottom: 10,
            }}
          >
            Runtime Contract Blocked
          </div>
          <h1 style={{ margin: "0 0 12px", fontSize: 28, lineHeight: 1.2 }}>
            当前部署与懒猫微服运行时不兼容
          </h1>
          <p style={{ margin: "0 0 20px", fontSize: 15, lineHeight: 1.7 }}>
            {assessment.reason ??
              "检测到前端静态包和宿主机 Verge API 的运行时契约不一致，已阻止继续启动。"}
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 12,
              marginBottom: 18,
            }}
          >
            <div
              style={{
                background: "#f7f9fc",
                borderRadius: 14,
                padding: "14px 16px",
              }}
            >
              <div style={{ fontSize: 12, color: "#7a8699", marginBottom: 8 }}>
                Expected
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.7 }}>
                <div>Build: {assessment.expected.buildId}</div>
                <div>Commit: {assessment.expected.gitCommit}</div>
                <div>API: {assessment.expected.apiSchemaVersion}</div>
                <div>UI: {assessment.expected.uiSchemaVersion}</div>
              </div>
            </div>
            <div
              style={{
                background: "#fff4f1",
                borderRadius: 14,
                padding: "14px 16px",
              }}
            >
              <div style={{ fontSize: 12, color: "#7a8699", marginBottom: 8 }}>
                Actual
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.7 }}>
                <div>Build: {actual?.buildId ?? "missing"}</div>
                <div>Commit: {actual?.gitCommit ?? "missing"}</div>
                <div>API: {actual?.apiSchemaVersion ?? "missing"}</div>
                <div>UI: {actual?.uiSchemaVersion ?? "missing"}</div>
              </div>
            </div>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: "#5a6473" }}>
            需要重新部署同一产物构建出的 dashboard LPK 与{" "}
            <code>mihomo-verge-api</code>，然后刷新页面。
          </p>
        </div>
      </div>
    </React.StrictMode>,
  );
};

const bootstrap = async () => {
  const assessment = assessRuntimeContract(getRuntimeInfo());
  persistRuntimeAssessment(assessment);

  if (assessment.status === "blocked") {
    renderRuntimeBlocked(assessment);
    return;
  }

  const { initialThemeMode } = await preloadAppData();
  initializeApp(initialThemeMode);
};

bootstrap().catch((error) => {
  console.error(
    "[main.tsx] App bootstrap failed, falling back to default language:",
    error,
  );
  initializeLanguage(FALLBACK_LANGUAGE)
    .catch((fallbackError) => {
      console.error(
        "[main.tsx] Fallback language initialization failed:",
        fallbackError,
      );
    })
    .finally(() => {
      initializeApp(resolveThemeMode(getPreloadConfig()));
    });
});

patchMonacoWorkerConsole();

// Error handling
window.addEventListener("error", (event) => {
  if (isIgnoredMonacoWorkerError(event.error ?? event.message)) {
    event.preventDefault();
    return;
  }
  console.error("[main.tsx] Global error:", event.error);
});

window.addEventListener("unhandledrejection", (event) => {
  if (isIgnoredMonacoWorkerError(event.reason)) {
    event.preventDefault();
    return;
  }
  console.error("[main.tsx] Unhandled promise rejection:", event.reason);
});

// Page close/refresh events
window.addEventListener("beforeunload", () => {
  // Clean up all WebSocket instances to prevent memory leaks
  MihomoWebSocket.cleanupAll();
});

// Page loaded event
window.addEventListener("DOMContentLoaded", () => {
  // Clean up all WebSocket instances to prevent memory leaks
  MihomoWebSocket.cleanupAll();
});
