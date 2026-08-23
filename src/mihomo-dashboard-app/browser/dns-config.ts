export type DnsValidationOutcome =
  | { status: "valid" | "busy" }
  | { status: "invalid"; kind: string; message: string }
  | { status: "skipped"; reason: string };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export const normalizeDnsValidationOutcome = (
  value: unknown,
): DnsValidationOutcome => {
  if (Array.isArray(value) && typeof value[0] === "boolean") {
    const message =
      typeof value[1] === "string" ? value[1] : String(value[1] ?? "");
    if (value[0]) {
      return { status: "valid" };
    }
    return {
      status: "invalid",
      kind: "config",
      message: message || "DNS configuration validation failed.",
    };
  }

  if (isRecord(value)) {
    if (value.status === "valid" || value.status === "busy") {
      return { status: value.status };
    }
    if (
      value.status === "invalid" &&
      typeof value.kind === "string" &&
      typeof value.message === "string"
    ) {
      return {
        status: "invalid",
        kind: value.kind,
        message: value.message,
      };
    }
    if (value.status === "skipped" && typeof value.reason === "string") {
      return { status: "skipped", reason: value.reason };
    }
  }

  return {
    status: "skipped",
    reason: "DNS configuration validation returned an unsupported response.",
  };
};

export const readOptionalDnsString = (value: unknown): string =>
  typeof value === "string" ? value : "";

export const assignOptionalDnsString = (
  target: Record<string, unknown>,
  key: string,
  value: string,
) => {
  if (value.trim()) {
    target[key] = value;
  } else {
    delete target[key];
  }
};
