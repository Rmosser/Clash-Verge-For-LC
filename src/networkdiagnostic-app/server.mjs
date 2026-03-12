import http from "node:http";
import net from "node:net";
import dns from "node:dns/promises";

const PORT = Number(process.env.PORT || 8000);
const TCP_TIMEOUT_MS = Number(process.env.TCP_TIMEOUT_MS || 2500);

const ORIGIN_HOST = process.env.ORIGIN_HOST || "origin.lazycat.cloud";
const ORIGIN_DNSADDR_NAME =
  process.env.ORIGIN_DNSADDR_NAME || "_dnsaddr.origin.lazycat.cloud";
const SERVICE_DNS_SERVERS = splitCsv(
  process.env.SERVICE_DNS_SERVERS,
  ["172.18.0.1:1053", "223.5.5.5:53", "119.29.29.29:53"],
);
const LAZYCAT_PUBLIC_DOMAINS = splitCsv(
  process.env.LAZYCAT_PUBLIC_DOMAINS,
  [
    "dl.lazycatcloud.com",
    "dl.lazycatmicroserver.com",
    "appstore.api.lazycatmicroserver.com",
  ],
);
const RELAY_TARGETS = splitTargets(
  process.env.RELAY_TARGETS,
  [
    "origin.lazycat.cloud:443",
    "dl.lazycatcloud.com:443",
    "dl.lazycatmicroserver.com:443",
  ],
);
const NAT_PROBE_TARGETS = splitTargets(
  process.env.NAT_PROBE_TARGETS,
  [
    "origin.lazycat.cloud:443",
    "dl.lazycatcloud.com:443",
    "dl.lazycatmicroserver.com:443",
  ],
);
const IPV4_PROBE_HOST = process.env.IPV4_PROBE_HOST || ORIGIN_HOST;
const IPV6_PROBE_HOST = process.env.IPV6_PROBE_HOST || "www.baidu.com";

const ENDPOINTS = [
  "ByIPv4Routing",
  "ByIPv6Routing",
  "ByLzcRelays",
  "ByOrigin",
  "ByDNS",
  "ByNATType",
  "ByIPv6Connectivity",
  "ByLazycatDomains",
];

const SOLUTION = {
  origin: "/solutions/origin.html",
  domains: "/solutions/lazycat-domains.html",
  ipv4: "/solutions/ipv4-routing.html",
  ipv6: "/solutions/ipv6.html",
  relays: "/solutions/relays.html",
  nat: "/solutions/nat.html",
  dns: "/solutions/dns.html",
};

function splitCsv(value, fallback = []) {
  const parts = (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return parts.length ? parts : fallback;
}

function splitTargets(value, fallback = []) {
  return splitCsv(value, fallback).map((entry) => {
    const [host, portText] = entry.split(":");
    return {
      host,
      port: Number(portText || 443),
    };
  });
}

function ok(caveat = "") {
  return {
    Help: {
      Caveat: caveat,
      Problem: "",
      Solution: "",
    },
  };
}

function issue(problem, solution, error = "", caveat = "") {
  return {
    Error: error,
    Help: {
      Caveat: caveat,
      Problem: problem,
      Solution: solution,
    },
  };
}

function json(res, statusCode, data) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(data));
}

async function lookupWithResolver(host, rrtype, servers = []) {
  const resolver = new dns.Resolver();
  if (servers.length) {
    resolver.setServers(servers);
  }
  const method =
    rrtype === "TXT"
      ? resolver.resolveTxt.bind(resolver)
      : rrtype === "A"
        ? resolver.resolve4.bind(resolver)
        : resolver.resolve6.bind(resolver);
  return method(host);
}

async function lookupDefault(host, rrtype) {
  if (rrtype === "TXT") {
    return dns.resolveTxt(host);
  }
  if (rrtype === "A") {
    return dns.resolve4(host);
  }
  return dns.resolve6(host);
}

function flattenTxt(rows) {
  return rows.map((row) => row.join(""));
}

function parseDnsAddrRecords(records) {
  const endpoints = [];
  for (const record of records) {
    const match = record.match(/dnsaddr=\/ip(4|6)\/([^/]+)\/tcp\/(\d+)/i);
    if (!match) {
      continue;
    }
    endpoints.push({
      family: match[1] === "4" ? 4 : 6,
      host: match[2],
      port: Number(match[3]),
    });
  }
  return endpoints;
}

function connectTcp(ip, port, family) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({
      host: ip,
      port,
      family,
    });
    const cleanup = () => {
      socket.removeAllListeners();
      socket.destroy();
    };
    socket.setTimeout(TCP_TIMEOUT_MS);
    socket.once("connect", () => {
      cleanup();
      resolve();
    });
    socket.once("timeout", () => {
      cleanup();
      reject(new Error(`timeout ${ip}:${port}`));
    });
    socket.once("error", (error) => {
      cleanup();
      reject(error);
    });
  });
}

async function tryAll(label, attempts) {
  const errors = [];
  for (const attempt of attempts) {
    try {
      const value = await attempt();
      return { ok: true, value, errors };
    } catch (error) {
      errors.push(`${label}: ${formatError(error)}`);
    }
  }
  return { ok: false, errors };
}

async function resolveAddresses(host, family = 0, servers = null) {
  const recordTypes = family === 6 ? ["AAAA"] : family === 4 ? ["A"] : ["A", "AAAA"];
  const addresses = [];
  const errors = [];

  for (const rrtype of recordTypes) {
    try {
      const values = servers
        ? await lookupWithResolver(host, rrtype, servers)
        : await lookupDefault(host, rrtype);
      for (const value of values) {
        addresses.push({
          address: value,
          family: rrtype === "AAAA" ? 6 : 4,
        });
      }
    } catch (error) {
      errors.push(`${rrtype} ${host}: ${formatError(error)}`);
    }
  }

  return { addresses, errors };
}

async function probeResolvedHost(host, port, family = 0, server = null) {
  const { addresses, errors } = await resolveAddresses(
    host,
    family,
    server ? [server] : null,
  );
  if (!addresses.length) {
    throw new Error(errors.join("; ") || `no address for ${host}`);
  }
  const attemptErrors = [];
  for (const item of addresses) {
    try {
      await connectTcp(item.address, port, item.family);
      return { via: item.address, family: item.family };
    } catch (error) {
      attemptErrors.push(`${item.address}:${port}: ${formatError(error)}`);
    }
  }
  throw new Error(attemptErrors.join("; "));
}

async function probeTargetList(targets, family = 0) {
  const errors = [];
  for (const target of targets) {
    try {
      await probeResolvedHost(target.host, target.port, family);
      return;
    } catch (error) {
      errors.push(`${target.host}:${target.port}: ${formatError(error)}`);
    }
  }
  throw new Error(errors.join("; "));
}

async function resolveOriginByDefault() {
  const rows = await lookupDefault(ORIGIN_DNSADDR_NAME, "TXT");
  const records = flattenTxt(rows);
  if (!records.length) {
    throw new Error("no dnsaddr TXT answer from default resolver");
  }
  return records;
}

async function resolveOriginByFallback() {
  const errors = [];
  for (const server of SERVICE_DNS_SERVERS) {
    try {
      const rows = await lookupWithResolver(ORIGIN_DNSADDR_NAME, "TXT", [server]);
      const records = flattenTxt(rows);
      if (records.length) {
        return { records, server };
      }
      errors.push(`${server}: empty TXT answer`);
    } catch (error) {
      errors.push(`${server}: ${formatError(error)}`);
    }
  }
  throw new Error(errors.join("; "));
}

async function checkOrigin() {
  try {
    await resolveOriginByDefault();
    return ok();
  } catch (defaultError) {
    try {
      const { records } = await resolveOriginByFallback();
      const endpoints = parseDnsAddrRecords(records);
      if (endpoints.length) {
        const endpointErrors = [];
        for (const endpoint of endpoints) {
          try {
            await connectTcp(endpoint.host, endpoint.port, endpoint.family);
            return ok();
          } catch (error) {
            endpointErrors.push(
              `${endpoint.host}:${endpoint.port}: ${formatError(error)}`,
            );
          }
        }
        try {
          await probeResolvedHost(ORIGIN_HOST, 443);
          return ok();
        } catch (serviceError) {
          return issue(
            "Cannot connect to origin server, you may not be able to connect to microserver outside LAN.",
            SOLUTION.origin,
            [
              formatError(defaultError),
              ...endpointErrors,
              formatError(serviceError),
            ].join("; "),
          );
        }
      }
      await probeResolvedHost(ORIGIN_HOST, 443);
      return ok();
    } catch (fallbackError) {
      try {
        await probeResolvedHost(ORIGIN_HOST, 443);
        return ok();
      } catch (serviceError) {
        return issue(
          "Cannot connect to origin server, you may not be able to connect to microserver outside LAN.",
          SOLUTION.origin,
          [
            formatError(defaultError),
            formatError(fallbackError),
            formatError(serviceError),
          ].join("; "),
        );
      }
    }
  }
}

async function checkLazycatDomains() {
  const errors = [];
  for (const domain of LAZYCAT_PUBLIC_DOMAINS) {
    try {
      await probeResolvedHost(domain, 443);
    } catch (error) {
      errors.push(`${domain}: ${formatError(error)}`);
    }
  }
  if (!errors.length) {
    return ok();
  }
  return issue(
    "Cannot connect to LazyCat public servers, app discovery or downloads may be impacted.",
    SOLUTION.domains,
    errors.join("; "),
  );
}

async function checkIPv4Routing() {
  try {
    await probeResolvedHost(IPV4_PROBE_HOST, 443, 4);
    return ok();
  } catch (error) {
    return issue(
      "TUN or TPROXY is enabled for IPv4, this may impact microserver connections in unexpected ways.",
      SOLUTION.ipv4,
      formatError(error),
    );
  }
}

async function checkIPv6Routing() {
  try {
    await probeResolvedHost(IPV6_PROBE_HOST, 443, 6);
    return ok();
  } catch (defaultError) {
    const errors = [formatError(defaultError)];
    for (const server of SERVICE_DNS_SERVERS) {
      try {
        await probeResolvedHost(IPV6_PROBE_HOST, 443, 6, server);
        return ok();
      } catch (error) {
        errors.push(`${server}: ${formatError(error)}`);
      }
    }
    return issue(
      "TUN or TPROXY is enabled for IPv6, this may impact direct connections to microserver.",
      SOLUTION.ipv6,
      errors.join("; "),
    );
  }
}

async function checkRelays() {
  try {
    await probeTargetList(RELAY_TARGETS, 0);
    return ok();
  } catch (error) {
    return issue(
      "Cannot connect to relay servers, you may not be able to connect to microserver outside LAN.",
      SOLUTION.relays,
      formatError(error),
    );
  }
}

async function checkDNS() {
  const errors = [];
  try {
    await resolveOriginByDefault();
  } catch (error) {
    errors.push(`default TXT ${ORIGIN_DNSADDR_NAME}: ${formatError(error)}`);
  }

  for (const domain of [ORIGIN_HOST, ...LAZYCAT_PUBLIC_DOMAINS]) {
    const { addresses, errors: resolveErrors } = await resolveAddresses(domain, 0);
    if (!addresses.length) {
      errors.push(...resolveErrors);
    }
  }

  if (!errors.length) {
    return ok();
  }

  try {
    await resolveOriginByFallback();
    return ok();
  } catch (error) {
    errors.push(`fallback TXT ${ORIGIN_DNSADDR_NAME}: ${formatError(error)}`);
    return issue(
      "DNS resolution is abnormal, microserver service discovery may be impacted.",
      SOLUTION.dns,
      errors.join("; "),
    );
  }
}

async function checkNATType() {
  try {
    await probeTargetList(NAT_PROBE_TARGETS, 4);
    return ok();
  } catch (error) {
    return issue(
      "Direct connection probe failed, direct connection may be impacted.",
      SOLUTION.nat,
      formatError(error),
    );
  }
}

async function checkIPv6Connectivity() {
  try {
    await probeResolvedHost(IPV6_PROBE_HOST, 443, 6);
    return ok();
  } catch (defaultError) {
    const errors = [formatError(defaultError)];
    for (const server of SERVICE_DNS_SERVERS) {
      try {
        await probeResolvedHost(IPV6_PROBE_HOST, 443, 6, server);
        return ok();
      } catch (error) {
        errors.push(`${server}: ${formatError(error)}`);
      }
    }
    return issue(
      "You don't have IPv6 connectivity, direct connection may be impacted.",
      SOLUTION.ipv6,
      errors.join("; "),
    );
  }
}

function formatError(error) {
  if (!error) {
    return "unknown error";
  }
  if (error.code) {
    return `${error.code}: ${error.message}`;
  }
  return error.message || String(error);
}

const CHECKS = {
  ByIPv4Routing: checkIPv4Routing,
  ByIPv6Routing: checkIPv6Routing,
  ByLzcRelays: checkRelays,
  ByOrigin: checkOrigin,
  ByDNS: checkDNS,
  ByNATType: checkNATType,
  ByIPv6Connectivity: checkIPv6Connectivity,
  ByLazycatDomains: checkLazycatDomains,
};

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", "http://127.0.0.1");
    if (url.pathname === "/healthz") {
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/list-api") {
      return json(res, 200, ENDPOINTS);
    }

    const endpoint = url.pathname.replace(/^\/+/, "");
    const handler = CHECKS[endpoint];
    if (!handler) {
      return json(res, 404, issue("Unknown diagnostic endpoint.", SOLUTION.dns, endpoint));
    }

    const result = await handler();
    return json(res, 200, result);
  } catch (error) {
    return json(
      res,
      500,
      issue(
        "The diagnostic backend encountered an unexpected error.",
        SOLUTION.dns,
        formatError(error),
      ),
    );
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[networkdiagnostic] listening on :${PORT}`);
});
