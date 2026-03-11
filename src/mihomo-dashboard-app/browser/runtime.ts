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
};

export type UnsupportedWebFeature =
  | "lightweight-mode"
  | "system-service"
  | "uwp-tool";

type RegisteredFile = {
  file: File;
  objectUrl: string;
};

const eventTarget = new EventTarget();
const fileRegistry = new Map<string, RegisteredFile>();
const dragDropSetupFlag = "__lzc_drag_drop_ready__";

const normalizeBaseUrl = (value: string | undefined, fallback: string) =>
  (value && value.trim() ? value.trim() : fallback).replace(/\/+$/, "");

export const getLzcConfig = (): LzcConfig => {
  const raw = window.__LZCAPP_MIHOMO__ ?? {};
  return {
    secret: raw.secret ?? "",
    // Deprecated: the web port relies on the current LazyCat login session.
    vergeApiSecret: raw.vergeApiSecret ?? "",
    mihomoBaseUrl: normalizeBaseUrl(raw.mihomoBaseUrl, "/api"),
    vergeApiBaseUrl: normalizeBaseUrl(raw.vergeApiBaseUrl, "/verge-api"),
    appVersion: raw.appVersion ?? "2.4.7-webport.0"
  };
};

export const getAppVersion = () => getLzcConfig().appVersion;
export const isLzcWebRuntime = () => typeof window !== "undefined";

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
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
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
