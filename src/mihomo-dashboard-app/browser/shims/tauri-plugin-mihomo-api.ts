import {
  controllerFetch,
  controllerJson,
  getLzcConfig,
  vergeInvoke
} from "../runtime";

export type BaseConfig = IConfigData;
export type ProxyProvider = IProxyProviderItem;
export type RuleProvider = IRuleProviderItem;
export type Rule = {
  type: string;
  payload: string;
  proxy: string;
  size?: number;
};
export type RulesResponse = { rules: Rule[] };
export type Traffic = { up: number; down: number };
export type ProxyDelay = { delay: number };
export type LogLevel = "debug" | "info" | "warning" | "error" | "silent";
export type Message = { type: "Text"; data: string };

const encodeName = (value: string) => encodeURIComponent(value);

const put = (path: string, body?: unknown) =>
  controllerFetch(path, {
    method: "PUT",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });

const deleteReq = (path: string) =>
  controllerFetch(path, {
    method: "DELETE"
  });

const readJsonOk = async <T>(promise: Promise<Response>) => {
  const response = await promise;
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as T;
};

const wsBase = () => {
  const { mihomoBaseUrl, secret } = getLzcConfig();
  const url = new URL(
    mihomoBaseUrl.replace(/^\//, ""),
    window.location.origin.replace(/^http/, "ws")
  );
  if (secret) {
    url.searchParams.set("token", secret);
  }
  return url;
};

type Listener = (msg: Message) => void;

export class MihomoWebSocket {
  private listeners = new Set<Listener>();
  private static all = new Set<MihomoWebSocket>();

  constructor(private socket: WebSocket) {
    MihomoWebSocket.all.add(this);
    socket.addEventListener("message", (event) => {
      const message: Message = { type: "Text", data: String(event.data ?? "") };
      this.listeners.forEach((listener) => listener(message));
    });
    socket.addEventListener("close", () => {
      MihomoWebSocket.all.delete(this);
    });
    socket.addEventListener("error", () => {
      this.listeners.forEach((listener) =>
        listener({ type: "Text", data: "Websocket error" })
      );
    });
  }

  addListener(listener: Listener) {
    this.listeners.add(listener);
  }

  async close() {
    this.socket.close();
  }

  private static async connect(pathWithQuery: string) {
    const [pathname, rawQuery = ""] = pathWithQuery.split("?", 2);
    const url = wsBase();
    url.pathname = `${url.pathname.replace(/\/$/, "")}${pathname}`;
    if (rawQuery) {
      const query = new URLSearchParams(rawQuery);
      query.forEach((value, key) => {
        url.searchParams.set(key, value);
      });
    }
    const socket = new WebSocket(url.toString());
    await new Promise<void>((resolve, reject) => {
      socket.addEventListener("open", () => resolve(), { once: true });
      socket.addEventListener("error", () => reject(new Error("websocket connection failed")), {
        once: true
      });
    });
    return new MihomoWebSocket(socket);
  }

  static connect_traffic() {
    return MihomoWebSocket.connect("/traffic");
  }

  static connect_memory() {
    return MihomoWebSocket.connect("/memory");
  }

  static connect_connections() {
    return MihomoWebSocket.connect("/connections");
  }

  static connect_logs(level: LogLevel) {
    return MihomoWebSocket.connect(`/logs?level=${encodeURIComponent(level)}`);
  }

  static cleanupAll() {
    MihomoWebSocket.all.forEach((socket) => {
      socket.close().catch(() => {});
    });
    MihomoWebSocket.all.clear();
  }
}

export const getVersion = () => controllerJson<{ version: string; meta?: boolean }>("/version");
export const getBaseConfig = async () => {
  const data = await controllerJson<BaseConfig>("/configs");
  return {
    ...data,
    mixedPort: data["mixed-port"],
    socksPort: data["socks-port"],
    redirPort: data["redir-port"],
    tproxyPort: data["tproxy-port"]
  };
};
export const getRules = async (): Promise<RulesResponse> => {
  const data = await controllerJson<RulesResponse>("/rules");
  return { rules: data.rules ?? [] };
};
export const getRuleProviders = async () => {
  const data = await controllerJson<{ providers: Record<string, RuleProvider> }>(
    "/providers/rules"
  );
  return data.providers ?? {};
};
export const getProxies = () =>
  controllerJson<{ proxies: Record<string, IProxyItem> }>("/proxies");
export const getProxyProviders = () =>
  controllerJson<{ providers: Record<string, ProxyProvider> }>("/providers/proxies");
export const getConnections = () => controllerJson<IConnections>("/connections");
export const closeAllConnections = async () => {
  await deleteReq("/connections");
};
export const closeConnection = async (id: string) => {
  await deleteReq(`/connections/${encodeName(id)}`);
};
export const selectNodeForGroup = async (group: string, proxy: string) => {
  await put(`/proxies/${encodeName(group)}`, { name: proxy });
};
export const updateProxyProvider = async (provider: string) => {
  const response = await put(`/providers/proxies/${encodeName(provider)}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
};
export const updateRuleProvider = async (provider: string) => {
  const response = await put(`/providers/rules/${encodeName(provider)}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
};
export const healthcheckProxyProvider = async (provider: string) => {
  const response = await put(`/providers/proxies/${encodeName(provider)}/healthcheck`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
};
export const delayProxyByName = async (
  name: string,
  url = "http://cp.cloudflare.com",
  timeout = 10000
): Promise<ProxyDelay> =>
  readJsonOk<ProxyDelay>(
    controllerFetch(
      `/proxies/${encodeName(name)}/delay?timeout=${timeout}&url=${encodeURIComponent(url)}`
    )
  );
export const delayGroup = delayProxyByName;
export const updateGeo = async () => {
  await vergeInvoke("update_geo", {});
};
export const upgradeCore = async () => {
  await vergeInvoke("upgrade_core", {});
};
