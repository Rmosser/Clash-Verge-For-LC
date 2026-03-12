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

const classifyProbeFailure = (
  rawText: string,
  status: number,
): Pick<ProbeEnvelope, "code" | "message"> => {
  const text = rawText.trim();
  const upper = text.toUpperCase();

  if (upper.includes("ETIMEDOUT") || upper.includes("TIMEOUT")) {
    return {
      code: "TIMEOUT",
      message: text || "探测超时。",
    };
  }

  if (
    upper.includes("ECONNREFUSED") ||
    upper.includes("ECONNRESET") ||
    upper.includes("EHOSTUNREACH") ||
    upper.includes("ENETUNREACH")
  ) {
    return {
      code: "PROXY_UNREACHABLE",
      message: text || "探测代理不可达。",
    };
  }

  if (upper.includes("TLS") || upper.includes("SSL")) {
    return {
      code: "UPSTREAM_TLS",
      message: text || "上游 TLS 握手失败。",
    };
  }

  return {
    code: "UNKNOWN",
    message: text || `HTTP ${status}`,
  };
};

const buildProbeEnvelope = <T>(
  response: Response,
  rawText: string,
): ProbeEnvelope<T> => {
  const failure = classifyProbeFailure(rawText, response.status);
  return {
    ok: false,
    code: failure.code,
    message: failure.message,
    durationMs: 0,
    fromCache: false,
  };
};

const parseProbeResponse = async <T>(response: Response) => {
  let payload: ProbeEnvelope<T> | null = null;
  const rawText = await response.text();

  try {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      payload = JSON.parse(rawText) as ProbeEnvelope<T>;
    } else {
      payload = buildProbeEnvelope<T>(response, rawText);
    }
  } catch (error) {
    payload = buildProbeEnvelope<T>(
      response,
      rawText || extractErrorMessage(error) || "探测响应解析失败。",
    );
  }

  if (!response.ok || !payload.ok) {
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
