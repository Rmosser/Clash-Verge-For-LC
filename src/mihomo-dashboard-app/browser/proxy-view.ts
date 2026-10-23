import yaml from "js-yaml";

import type {
  ProxyViewV1,
  ProxyNodeView,
  ProxyGroupView,
  ProxyMemberRef,
} from "../vendor/clash-verge-rev/src/types/proxy-view";

import {
  controllerJson,
  vergeInvoke,
  vergeJson,
  type RuntimeInfo,
} from "./runtime";

type Raw = Record<string, any>;
export function buildProxyView(
  proxies: Record<string, Raw>,
  providers: Record<string, Raw> | null,
  runtime: Raw,
): ProxyViewV1 {
  const records: ProxyViewV1["records"] = {};
  const core = new Map<string, string>();
  const candidates = new Map<string, string[]>();
  const groupNames = new Set(
    Object.keys(proxies).filter((name) => Array.isArray(proxies[name].all)),
  );
  const details = (name: string, p: Raw) => ({
    ...p,
    name,
    type: p.type ?? "Unknown",
    alive: p.alive ?? true,
    history: p.history ?? [],
    udp: !!p.udp,
    xudp: !!p.xudp,
    tfo: !!p.tfo,
    mptcp: !!p.mptcp,
    smux: !!p.smux,
    testUrl: p.testUrl ?? p["test-url"],
  });
  for (const [name, p] of Object.entries(proxies)) {
    if (groupNames.has(name) || (providers && p["provider-name"])) continue;
    const recordId = JSON.stringify(["core", name]);
    core.set(name, recordId);
    records[recordId] = {
      ...details(name, p),
      recordId,
      source: { kind: "core", proxyName: name },
    };
  }
  const providerViews = Object.entries(providers ?? {})
    .filter(([, p]) => ["HTTP", "File", "Inline"].includes(p.vehicleType))
    .map(([name, p]) => ({
      name,
      vehicleType: p.vehicleType,
      updatedAt: p.updatedAt,
      subscriptionInfo: p.subscriptionInfo,
      proxyRecordIds: (p.proxies ?? []).map((node: Raw, index: number) => {
        const recordId = JSON.stringify(["provider", name, node.name, index]);
        records[recordId] = {
          ...details(node.name, node),
          recordId,
          source: {
            kind: "provider",
            providerName: name,
            proxyName: node.name,
          },
        };
        candidates.set(node.name, [
          ...(candidates.get(node.name) ?? []),
          recordId,
        ]);
        return recordId;
      }),
    }));
  const scopes: Raw[] = Array.isArray(runtime["proxy-groups"])
    ? runtime["proxy-groups"]
    : [];
  const buildGroup = (name: string): ProxyGroupView => {
    const scope = scopes.find((s) => s.name === name);
    const seen = new Map<string, number>();
    const members = proxies[name].all.map((member: string): ProxyMemberRef => {
      if (groupNames.has(member)) return { kind: "group", name: member };
      if (core.has(member))
        return { kind: "node", name: member, recordId: core.get(member)! };
      const all = candidates.get(member) ?? [];
      const excluded = String(scope?.["exclude-type"] ?? "")
        .toLowerCase()
        .split("|");
      const scoped = (scope?.use ?? []).flatMap((provider: string) =>
        all.filter((id) => {
          const node: ProxyNodeView = records[id];
          return (
            node.source.kind === "provider" &&
            node.source.providerName === provider &&
            !excluded.includes(node.type.toLowerCase())
          );
        }),
      );
      const index = seen.get(member) ?? 0;
      seen.set(member, index + 1);
      const recordId =
        scoped[index] ?? scoped[0] ?? (all.length === 1 ? all[0] : undefined);
      return recordId
        ? { kind: "node", name: member, recordId }
        : {
            kind: "unresolved",
            name: member,
            reason: !providers
              ? "provider-unavailable"
              : all.length
                ? "ambiguous"
                : "missing",
          };
    });
    return { ...details(name, proxies[name]), members };
  };
  const order = scopes
    .map((s) => s.name)
    .filter((name) => groupNames.has(name) && name !== "GLOBAL");
  const names = [...new Set([...order, ...groupNames])].filter(
    (name) => name !== "GLOBAL",
  );
  return {
    schemaVersion: 1,
    orderSource: order.length ? "runtime" : "fallback",
    providerState: providers ? "ready" : "unavailable",
    global: groupNames.has("GLOBAL") ? buildGroup("GLOBAL") : null,
    direct: core.get("DIRECT") ?? null,
    groups: names.map(buildGroup),
    records,
    standalone: [...core.values()],
    providers: providerViews,
  };
}
let lastGood: ProxyViewV1 | undefined;
export async function getWebProxyView(): Promise<ProxyViewV1> {
  const health = await vergeJson<RuntimeInfo>("/runtime-info");
  if (health.profileHealth?.status === "degraded" && lastGood) return lastGood;
  const [proxyResponse, providerResponse, text] = await Promise.all([
    controllerJson<{ proxies: Record<string, Raw> }>("/proxies"),
    controllerJson<{ providers: Record<string, Raw> }>(
      "/providers/proxies",
    ).catch(() => null),
    vergeInvoke<string>("get_runtime_yaml", {}),
  ]);
  const runtime = yaml.load(text);
  const view = buildProxyView(
    proxyResponse.proxies,
    providerResponse?.providers ?? null,
    runtime && typeof runtime === "object" ? (runtime as Raw) : {},
  );
  if (health.profileHealth?.status !== "degraded") lastGood = view;
  return view;
}
