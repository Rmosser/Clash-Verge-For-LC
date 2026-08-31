export type SystemInfo = {
  system_name: string;
  system_version: string;
  system_kernel_version: string;
  system_arch: string;
  app_version: string;
  app_core_mode: string;
  app_is_admin: boolean;
};

export type DelayProbeResponse = {
  target?: string | null;
  status?: DelayProbeStatus | null;
  latencyMs?: number | null;
  delay?: number | null;
  errorCode?: string | null;
  errorMessage?: string | null;
};

type DelayProbeStatus =
  | "success"
  | "timeout"
  | "failed"
  | "error"
  | "network_error"
  | "target_unreachable";

const DELAY_PROBE_STATUSES: ReadonlySet<string> = new Set([
  "success",
  "timeout",
  "failed",
  "error",
  "network_error",
  "target_unreachable",
]);

const EMPTY_SYSTEM_INFO: SystemInfo = {
  system_name: "",
  system_version: "",
  system_kernel_version: "",
  system_arch: "",
  app_version: "",
  app_core_mode: "",
  app_is_admin: false,
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const finiteNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const finiteNonNegativeNumber = (value: unknown): number | null => {
  const number = finiteNumber(value);
  return number !== null && number >= 0 ? number : null;
};

const stringValue = (value: unknown) =>
  typeof value === "string" ? value : "";

const isOptionalString = (value: unknown) =>
  value === undefined || value === null || typeof value === "string";

const isOptionalDelayProbeStatus = (value: unknown) => {
  if (value === undefined || value === null) return true;
  if (typeof value !== "string") return false;
  return DELAY_PROBE_STATUSES.has(value.toLowerCase());
};

const isOptionalFiniteNumber = (value: unknown) =>
  value === undefined || value === null || finiteNumber(value) !== null;

const isDelayProbeResponse = (value: unknown): value is DelayProbeResponse => {
  if (!isRecord(value)) return false;
  return (
    isOptionalString(value.target) &&
    isOptionalDelayProbeStatus(value.status) &&
    isOptionalFiniteNumber(value.latencyMs) &&
    isOptionalFiniteNumber(value.delay) &&
    isOptionalString(value.errorCode) &&
    isOptionalString(value.errorMessage)
  );
};

const normalizeSystemInfoObject = (
  value: Record<string, unknown>,
): SystemInfo => ({
  system_name: stringValue(value.system_name),
  system_version: stringValue(value.system_version),
  system_kernel_version: stringValue(value.system_kernel_version),
  system_arch: stringValue(value.system_arch),
  app_version: stringValue(value.app_version),
  app_core_mode: stringValue(value.app_core_mode),
  app_is_admin: value.app_is_admin === true,
});

const normalizeSystemInfoText = (value: string): SystemInfo => {
  const fields = new Map<string, string>();
  value.split(/\r?\n/).forEach((line) => {
    const separator = line.indexOf(":");
    if (separator < 0) return;

    const key = line.slice(0, separator).trim();
    if (!key) return;
    fields.set(key, line.slice(separator + 1).trim());
  });

  return {
    ...EMPTY_SYSTEM_INFO,
    system_name: fields.get("System Name") ?? "",
    system_version: fields.get("System Version") ?? "",
    system_kernel_version: fields.get("Kernel Version") ?? "",
  };
};

/**
 * The WebPort command currently returns the output of current_system_info_text
 * rather than the object returned by the desktop Tauri command. Keep the
 * vendored UI contract stable and never expose undefined fields to it.
 */
export const normalizeSystemInfo = (value: unknown): SystemInfo => {
  if (typeof value === "string") {
    return normalizeSystemInfoText(value);
  }
  if (isRecord(value)) {
    return normalizeSystemInfoObject(value);
  }
  return { ...EMPTY_SYSTEM_INFO };
};

/**
 * The WebPort test_delay command returns a probe object, while the vendored
 * TestItem consumes the desktop command's numeric delay contract.
 *
 * - successful latency is returned as milliseconds;
 * - timeout keeps the existing UI's 0 => Timeout convention;
 * - other explicit failures keep the existing >1e5 => Error convention;
 * - an empty or malformed successful response remains untested (-1), rather
 *   than rendering a fabricated 0ms result.
 */
export const normalizeTestDelay = (value: unknown): number => {
  const legacyNumber = finiteNumber(value);
  if (legacyNumber !== null) return legacyNumber;
  if (!isDelayProbeResponse(value)) return -1;

  const status = stringValue(value.status).toLowerCase();
  const errorCode = stringValue(value.errorCode).toLowerCase();
  if (status === "timeout" || errorCode === "timeout") return 0;
  if (
    status === "failed" ||
    status === "error" ||
    status === "network_error" ||
    status === "target_unreachable" ||
    errorCode
  ) {
    return 1_000_000;
  }
  if (status && status !== "success") return -1;

  const latencyMs = finiteNonNegativeNumber(value.latencyMs);
  if (latencyMs !== null) return latencyMs;

  const legacyDelay = finiteNonNegativeNumber(value.delay);
  if (legacyDelay !== null) return legacyDelay;

  return -1;
};
