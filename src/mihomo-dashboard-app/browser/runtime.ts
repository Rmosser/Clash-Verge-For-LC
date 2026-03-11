import runtimeContract from "../runtime-contract.json";

type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

type LzcConfig = {
  secret: string;
  vergeApiSecret: string;
  mihomoBaseUrl: string;
  vergeApiBaseUrl: string;
  appVersion: string;
  runtimeInfo: RuntimeInfo | null;
  runtimeWarning: RuntimeContractWarning | null;
};

export type UnsupportedWebFeature =
  | "lightweight-mode"
  | "system-service"
  | "uwp-tool";

export type WebCapability =
  | "externalOpen"
  | "clipboard"
  | "download"
  | "filePicker"
  | "directoryOpen"
  | "devtools"
  | "lightweightMode"
  | "systemService"
  | "windowDecorations"
  | "tray";

export type WebActionPolicy = {
  mode: "enabled" | "degraded" | "disabled";
  reason: string;
  label?: string;
  fallback?: string;
};

export type WebCommandResult<T = unknown> = {
  kind: "success" | "degraded" | "unsupported" | "error";
  message?: string;
  data?: T;
};

export type RuntimeInfo = {
  platform: string;
  appVersion: string;
  buildId: string;
  gitCommit: string;
  apiSchemaVersion: string;
  uiSchemaVersion: string;
  packageFingerprint: string;
  capabilities: Record<WebCapability, WebActionPolicy>;
  probeHealth?: {
    status: "ok" | "degraded";
    checkedAt: string;
    details?: string;
  };
};

export type RuntimeContractWarning = {
  code: "DEPLOYMENT_DRIFT";
  message: string;
  expected: Pick<RuntimeInfo, "buildId" | "gitCommit">;
  actual: Pick<RuntimeInfo, "buildId" | "gitCommit">;
};

export type RuntimeContractStatus = "ready" | "warning" | "blocked";

export type RuntimeContractAssessment = {
  status: RuntimeContractStatus;
  reason?: string;
  warning?: RuntimeContractWarning;
  expected: RuntimeInfo;
  actual: RuntimeInfo | null;
};

type RuntimeContractConfig = RuntimeInfo;

type RegisteredFile = {
  file: File;
  objectUrl: string;
};

const eventTarget = new EventTarget();
const fileRegistry = new Map<string, RegisteredFile>();
const dragDropSetupFlag = "__lzc_drag_drop_ready__";
const EXPECTED_RUNTIME_INFO = runtimeContract as RuntimeContractConfig;

const normalizeBaseUrl = (value: string | undefined, fallback: string) =>
  (value && value.trim() ? value.trim() : fallback).replace(/\/+$/, "");

export const getLzcConfig = (): LzcConfig => {
  const raw = window.__LZCAPP_MIHOMO__ ?? {};
  const runtimeInfo = isRuntimeInfo(raw.runtimeInfo) ? raw.runtimeInfo : null;
  const runtimeWarning = isRuntimeContractWarning(raw.runtimeWarning)
    ? raw.runtimeWarning
    : null;
  return {
    secret: raw.secret ?? "",
    // Deprecated: the web port relies on the current LazyCat login session.
    vergeApiSecret: raw.vergeApiSecret ?? "",
    mihomoBaseUrl: normalizeBaseUrl(raw.mihomoBaseUrl, "/api"),
    vergeApiBaseUrl: normalizeBaseUrl(raw.vergeApiBaseUrl, "/verge-api"),
    appVersion: raw.appVersion ?? EXPECTED_RUNTIME_INFO.appVersion,
    runtimeInfo,
    runtimeWarning
  };
};

export const getAppVersion = () => getLzcConfig().appVersion;
export const isLzcWebRuntime = () => typeof window !== "undefined";
export const getExpectedRuntimeInfo = () => EXPECTED_RUNTIME_INFO;
export const getRuntimeInfo = () => getLzcConfig().runtimeInfo;
export const getRuntimeContractWarning = () => getLzcConfig().runtimeWarning;

export const getUnsupportedWebFeatureMessage = (
  feature: UnsupportedWebFeature
) => {
  switch (feature) {
    case "lightweight-mode":
      return "LazyCat Web 版不支持桌面轻量模式，请使用桌面版 Clash Verge。";
    case "system-service":
      return "LazyCat Web 版不支持安装、卸载或修复本机系统服务。";
    case "uwp-tool":
      return "LazyCat Web 版不支持 UWP Tool。";
    default:
      return "LazyCat Web 版不支持该桌面专属功能。";
  }
};

const WEB_ACTION_POLICIES: Record<WebCapability, WebActionPolicy> =
  EXPECTED_RUNTIME_INFO.capabilities;

export const getWebActionPolicy = (
  capability: WebCapability
): WebActionPolicy => WEB_ACTION_POLICIES[capability];

export const assessRuntimeContract = (
  actualRuntime: RuntimeInfo | null
): RuntimeContractAssessment => {
  if (!actualRuntime) {
    return {
      status: "blocked",
      reason: "未获取到运行时清单，当前部署不可安全启动。",
      expected: EXPECTED_RUNTIME_INFO,
      actual: null
    };
  }

  if (actualRuntime.platform !== EXPECTED_RUNTIME_INFO.platform) {
    return {
      status: "blocked",
      reason: `运行平台不匹配：期望 ${EXPECTED_RUNTIME_INFO.platform}，实际 ${actualRuntime.platform}。`,
      expected: EXPECTED_RUNTIME_INFO,
      actual: actualRuntime
    };
  }

  if (
    actualRuntime.apiSchemaVersion !== EXPECTED_RUNTIME_INFO.apiSchemaVersion ||
    actualRuntime.uiSchemaVersion !== EXPECTED_RUNTIME_INFO.uiSchemaVersion
  ) {
    return {
      status: "blocked",
      reason:
        "前后端运行时契约版本不匹配，请重新部署匹配的 dashboard LPK 与 mihomo-verge-api。",
      expected: EXPECTED_RUNTIME_INFO,
      actual: actualRuntime
    };
  }

  if (
    actualRuntime.packageFingerprint !== EXPECTED_RUNTIME_INFO.packageFingerprint ||
    actualRuntime.appVersion !== EXPECTED_RUNTIME_INFO.appVersion
  ) {
    return {
      status: "blocked",
      reason:
        "部署包指纹不匹配，当前静态资源与宿主机 Verge API 不是同一套版本。",
      expected: EXPECTED_RUNTIME_INFO,
      actual: actualRuntime
    };
  }

  if (
    actualRuntime.buildId !== EXPECTED_RUNTIME_INFO.buildId ||
    actualRuntime.gitCommit !== EXPECTED_RUNTIME_INFO.gitCommit
  ) {
    return {
      status: "warning",
      expected: EXPECTED_RUNTIME_INFO,
      actual: actualRuntime,
      warning: {
        code: "DEPLOYMENT_DRIFT",
        message:
          "检测到部署漂移：运行中的后端构建与当前前端包提交不一致，但契约仍兼容。",
        expected: {
          buildId: EXPECTED_RUNTIME_INFO.buildId,
          gitCommit: EXPECTED_RUNTIME_INFO.gitCommit
        },
        actual: {
          buildId: actualRuntime.buildId,
          gitCommit: actualRuntime.gitCommit
        }
      }
    };
  }

  return {
    status: "ready",
    expected: EXPECTED_RUNTIME_INFO,
    actual: actualRuntime
  };
};

export const isRuntimeContractWarning = (
  value: unknown
): value is RuntimeContractWarning =>
  !!value &&
  typeof value === "object" &&
  (value as { code?: unknown }).code === "DEPLOYMENT_DRIFT" &&
  typeof (value as { message?: unknown }).message === "string";

export const isRuntimeInfo = (value: unknown): value is RuntimeInfo => {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<RuntimeInfo>;
  return (
    typeof candidate.platform === "string" &&
    typeof candidate.appVersion === "string" &&
    typeof candidate.buildId === "string" &&
    typeof candidate.gitCommit === "string" &&
    typeof candidate.apiSchemaVersion === "string" &&
    typeof candidate.uiSchemaVersion === "string" &&
    typeof candidate.packageFingerprint === "string" &&
    !!candidate.capabilities &&
    typeof candidate.capabilities === "object"
  );
};

export const persistRuntimeAssessment = (
  assessment: RuntimeContractAssessment
) => {
  const mutableWindow = window as typeof window & {
    __LZCAPP_MIHOMO__?: Window["__LZCAPP_MIHOMO__"];
  };
  mutableWindow.__LZCAPP_MIHOMO__ = {
    ...(mutableWindow.__LZCAPP_MIHOMO__ ?? {}),
    runtimeInfo: assessment.actual ?? null,
    runtimeWarning: assessment.warning ?? null
  };
};

export const createWebCommandResult = <T>(
  kind: WebCommandResult<T>["kind"],
  message?: string,
  data?: T
): WebCommandResult<T> => {
  const result: WebCommandResult<T> = { kind };
  if (message) {
    result.message = message;
  }
  if (data !== undefined) {
    result.data = data;
  }
  return result;
};

export const isWebCommandResult = (value: unknown): value is WebCommandResult =>
  !!value &&
  typeof value === "object" &&
  typeof (value as { kind?: unknown }).kind === "string";

type RuntimeErrorEnvelope = {
  code?: string;
  message?: string;
  layer?: string;
  recoverable?: boolean;
  warning?: unknown;
  data?: unknown;
};

const buildHeaders = (
  initHeaders: HeadersInit | undefined,
  bearerToken: string | undefined
) => {
  const headers = new Headers(initHeaders ?? {});
  if (bearerToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${bearerToken}`);
  }
  return headers;
};

const parseJsonResponse = async <T>(response: Response): Promise<T> => {
  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;

  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }

  if (!response.ok) {
    const envelope =
      payload && typeof payload === "object"
        ? (payload as RuntimeErrorEnvelope)
        : null;
    const message =
      (typeof envelope?.message === "string" && envelope.message) ||
      (typeof payload === "string" && payload) ||
      `HTTP ${response.status}`;
    const error = new Error(message) as Error & {
      status?: number;
      code?: string;
      layer?: string;
      recoverable?: boolean;
      warning?: unknown;
      data?: unknown;
    };
    error.status = response.status;
    if (envelope?.code) {
      error.code = envelope.code;
    }
    if (envelope?.layer) {
      error.layer = envelope.layer;
    }
    if (typeof envelope?.recoverable === "boolean") {
      error.recoverable = envelope.recoverable;
    }
    if (envelope?.warning !== undefined) {
      error.warning = envelope.warning;
    }
    if (envelope?.data !== undefined) {
      error.data = envelope.data;
    }
    throw error;
  }

  return payload as T;
};

export const controllerFetch = async (
  input: string,
  init?: RequestInit
) => {
  const { mihomoBaseUrl, secret } = getLzcConfig();
  return fetch(`${mihomoBaseUrl}${input}`, {
    ...init,
    credentials: init?.credentials ?? "same-origin",
    headers: buildHeaders(init?.headers, secret)
  });
};

export const controllerJson = async <T>(
  input: string,
  init?: RequestInit
): Promise<T> => parseJsonResponse<T>(await controllerFetch(input, init));

export const vergeFetch = async (input: string, init?: RequestInit) => {
  const { vergeApiBaseUrl, vergeApiSecret } = getLzcConfig();
  return fetch(`${vergeApiBaseUrl}${input}`, {
    ...init,
    credentials: init?.credentials ?? "same-origin",
    headers: buildHeaders(init?.headers, vergeApiSecret)
  });
};

export const vergeJson = async <T>(
  input: string,
  init?: RequestInit
): Promise<T> => parseJsonResponse<T>(await vergeFetch(input, init));

export const vergeInvoke = async <T>(
  cmd: string,
  args: Record<string, unknown> | undefined
): Promise<T> =>
  vergeJson<T>("/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, args: args ?? {} })
  });

export const dispatchAppEvent = <T>(eventName: string, payload: T) => {
  eventTarget.dispatchEvent(
    new CustomEvent<{ payload: T }>(eventName, { detail: { payload } })
  );
};

export const addAppEventListener = <T>(
  eventName: string,
  callback: (event: { payload: T }) => void
) => {
  const handler = (event: Event) => {
    const detail = (event as CustomEvent<{ payload: T }>).detail;
    callback({ payload: detail?.payload as T });
  };
  eventTarget.addEventListener(eventName, handler as EventListener);
  return () => eventTarget.removeEventListener(eventName, handler as EventListener);
};

const createFileToken = (file: File) =>
  `lzc-file://${Date.now()}-${crypto.randomUUID()}/${encodeURIComponent(file.name)}`;

export const registerFiles = (files: File[] | FileList) => {
  const list = Array.from(files);
  return list.map((file) => {
    const token = createFileToken(file);
    const existing = fileRegistry.get(token);
    if (existing) {
      URL.revokeObjectURL(existing.objectUrl);
    }
    fileRegistry.set(token, {
      file,
      objectUrl: URL.createObjectURL(file)
    });
    return token;
  });
};

export const getRegisteredFile = (token: string) => fileRegistry.get(token)?.file ?? null;

export const readRegisteredText = async (token: string) => {
  const file = getRegisteredFile(token);
  if (!file) {
    throw new Error(`No registered file for ${token}`);
  }
  return file.text();
};

export const readRegisteredBuffer = async (token: string) => {
  const file = getRegisteredFile(token);
  if (!file) {
    throw new Error(`No registered file for ${token}`);
  }
  return new Uint8Array(await file.arrayBuffer());
};

export const getRegisteredFileUrl = (token: string) =>
  fileRegistry.get(token)?.objectUrl ?? null;

export const isRegisteredFileToken = (value: string) => value.startsWith("lzc-file://");

export const toBase64 = (bytes: Uint8Array) => {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
};

export const textToBase64 = (text: string) =>
  toBase64(new TextEncoder().encode(text));

export const saveBlob = (blob: Blob, filename: string) => {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
};

export const resolveAppFileUrl = (path: string) => {
  if (!path) return "";
  if (/^(blob:|data:|https?:)/i.test(path)) return path;
  const local = getRegisteredFileUrl(path);
  if (local) return local;
  const { vergeApiBaseUrl } = getLzcConfig();
  const url = new URL(`${vergeApiBaseUrl}/file`, window.location.origin);
  url.searchParams.set("path", path);
  return url.toString();
};

const absoluteUrlPattern = /^https?:\/\//i;

export const proxyHttpFetch = async (
  input: string | URL | Request,
  init?: RequestInit & { connectTimeout?: number }
) => {
  const requestUrl =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;

  if (
    absoluteUrlPattern.test(requestUrl) &&
    !requestUrl.startsWith(window.location.origin)
  ) {
    const proxied = new URL("/fetch/", window.location.origin);
    proxied.searchParams.set("url", requestUrl);
    return fetch(proxied.toString(), {
      ...init,
      method: init?.method ?? "GET"
    });
  }

  return fetch(requestUrl, init);
};

export const ensureDragDropBridge = (eventName: string) => {
  if (eventName !== "tauri://drag-drop") return;
  const mutableWindow = window as unknown as Record<string, unknown>;
  if (mutableWindow[dragDropSetupFlag]) return;
  mutableWindow[dragDropSetupFlag] = true;

  const prevent = (event: DragEvent) => {
    event.preventDefault();
  };

  window.addEventListener("dragover", prevent);
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (!files?.length) return;
    const paths = registerFiles(files);
    dispatchAppEvent("tauri://drag-drop", { paths });
  });
};

export const splitPathSegments = (value: string) =>
  value
    .split(/[\\/]+/)
    .map((segment) => segment.trim())
    .filter(Boolean);

export const basename = (value: string) => {
  const segments = splitPathSegments(value);
  return segments[segments.length - 1] ?? value;
};

export const isPlainObject = (value: unknown): value is Record<string, JsonValue> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);
