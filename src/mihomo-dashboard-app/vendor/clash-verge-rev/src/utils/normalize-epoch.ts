const MILLISECOND_EPOCH_THRESHOLD = 1e11;

export const normalizeEpochToMs = (value?: number | null) => {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return 0;
  }

  // Some runtimes return epoch seconds while the LazyCat web runtime already
  // returns epoch milliseconds for profile.updated.
  return value >= MILLISECOND_EPOCH_THRESHOLD ? value : value * 1000;
};
