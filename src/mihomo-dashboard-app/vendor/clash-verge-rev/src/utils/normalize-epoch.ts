const MILLISECOND_EPOCH_THRESHOLD = 1e11;
const MAX_REASONABLE_EPOCH_MS = Date.UTC(2100, 0, 1);

export const normalizeEpochToMs = (value?: number | null) => {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return 0;
  }

  // Some runtimes return epoch seconds while the LazyCat web runtime already
  // returns epoch milliseconds for profile.updated.
  return value >= MILLISECOND_EPOCH_THRESHOLD ? value : value * 1000;
};

export const normalizePlausibleEpochToMs = (value?: number | null) => {
  const normalized = normalizeEpochToMs(value);
  if (!normalized || normalized > MAX_REASONABLE_EPOCH_MS) {
    return 0;
  }
  return normalized;
};
