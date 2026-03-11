import { invoke } from "@tauri-apps/api/core";
import { extractErrorMessage } from "foxts/extract-error-message";

export type ProbeCode =
  | "OK"
  | "TIMEOUT"
  | "UPSTREAM_TLS"
  | "PROXY_UNREACHABLE"
  | "NO_ACTIVE_PROXY"
  | "TARGET_BLOCKED"
  | "UNKNOWN";

export type ProbeEnvelope<T = unknown> = {
  ok: boolean;
  code: ProbeCode;
  message: string;
  data?: T;
  durationMs: number;
  fromCache: boolean;
};

export type ProbeRequest = {
  kind: "ip_info" | "unlock" | "url";
  target?: string;
  timeoutMs?: number;
  proxyGroup?: string;
};

const hasWebPortRuntime = () =>
  typeof window !== "undefined" &&
  !!window.__LZCAPP_MIHOMO__?.vergeApiBaseUrl;

export const createProbeError = (
  code: ProbeCode,
  message: string,
  payload?: unknown,
) => {
  const error = new Error(message) as Error & {
    code?: ProbeCode;
    payload?: unknown;
  };
  error.code = code;
  error.payload = payload;
  return error;
};

const parseProbeResponse = async <T>(response: Response) => {
  let payload: ProbeEnvelope<T> | null = null;

  try {
    payload = (await response.json()) as ProbeEnvelope<T>;
  } catch (error) {
    throw createProbeError(
      "UNKNOWN",
      extractErrorMessage(error) || "探测响应解析失败。",
    );
  }

  if (!response.ok) {
    throw createProbeError(
      payload?.code || "UNKNOWN",
      payload.message || "探测失败。",
      payload,
    );
  }

  return payload;
};

export const probeRuntime = async <T>(
  request: ProbeRequest,
): Promise<ProbeEnvelope<T>> => {
  if (hasWebPortRuntime()) {
    const response = await fetch("/fetch/probe", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });
    return parseProbeResponse<T>(response);
  }

  if (request.kind === "ip_info") {
    const result = await invoke<T>("get_ip_info");
    return {
      ok: true,
      code: "OK",
      message: "ok",
      data: result,
      durationMs: 0,
      fromCache: false,
    };
  }

  if (request.kind === "unlock") {
    const result = await invoke<T>("check_media_unlock");
    return {
      ok: true,
      code: "OK",
      message: "ok",
      data: result,
      durationMs: 0,
      fromCache: false,
    };
  }

  const result = await invoke<T>("test_delay", { url: request.target });
  return {
    ok: true,
    code: "OK",
    message: "ok",
    data: result,
    durationMs: 0,
    fromCache: false,
  };
};
