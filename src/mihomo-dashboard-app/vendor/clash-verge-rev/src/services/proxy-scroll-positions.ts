export const PROXY_SCROLL_POSITIONS_KEY = 'proxy-scroll-positions'
export const PROXY_SCROLL_POSITIONS_SCHEMA_VERSION = 2

const LEGACY_SCROLL_POSITION_KEYS = ['rule', 'global'] as const

type StoredScrollPositions = Record<string, unknown>

const getStorage = (): Storage | null => {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

const isRecord = (value: unknown): value is StoredScrollPositions =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isScrollPosition = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0

const legacyKeyFor = (scrollPositionKey: string) => {
  if (!scrollPositionKey.endsWith(':normal')) return null

  const mode = scrollPositionKey.slice(0, -':normal'.length)
  return LEGACY_SCROLL_POSITION_KEYS.includes(
    mode as (typeof LEGACY_SCROLL_POSITION_KEYS)[number],
  )
    ? mode
    : null
}

const clearStoredPositions = (storage: Storage) => {
  try {
    storage.removeItem(PROXY_SCROLL_POSITIONS_KEY)
  } catch {
    // Storage can be unavailable in private browsing or when quota is denied.
  }
}

const persistPositions = (storage: Storage, positions: StoredScrollPositions) => {
  try {
    storage.setItem(
      PROXY_SCROLL_POSITIONS_KEY,
      JSON.stringify(positions),
    )
  } catch (error) {
    console.error('Error saving scroll position:', error)
  }
}

const loadPositions = (storage: Storage): StoredScrollPositions | null => {
  let raw: string | null
  try {
    raw = storage.getItem(PROXY_SCROLL_POSITIONS_KEY)
  } catch {
    return null
  }
  if (!raw) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    clearStoredPositions(storage)
    return null
  }
  if (!isRecord(parsed)) {
    clearStoredPositions(storage)
    return null
  }

  if (
    parsed.version !== undefined &&
    parsed.version !== PROXY_SCROLL_POSITIONS_SCHEMA_VERSION
  ) {
    clearStoredPositions(storage)
    return null
  }

  const positions = { ...parsed }
  let changed = parsed.version !== PROXY_SCROLL_POSITIONS_SCHEMA_VERSION

  for (const legacyKey of LEGACY_SCROLL_POSITION_KEYS) {
    const newKey = `${legacyKey}:normal`
    if (!isScrollPosition(positions[newKey]) && isScrollPosition(positions[legacyKey])) {
      positions[newKey] = positions[legacyKey]
      changed = true
    }
    if (legacyKey in positions) {
      delete positions[legacyKey]
      changed = true
    }
  }

  positions.version = PROXY_SCROLL_POSITIONS_SCHEMA_VERSION
  if (changed) persistPositions(storage, positions)
  return positions
}

export const getProxyScrollPosition = (
  scrollPositionKey: string,
  storage = getStorage(),
): number | undefined => {
  if (!storage) return undefined

  const positions = loadPositions(storage)
  const savedPosition = positions?.[scrollPositionKey]
  return isScrollPosition(savedPosition) ? savedPosition : undefined
}

export const saveProxyScrollPosition = (
  scrollPositionKey: string,
  scrollTop: number,
  storage = getStorage(),
) => {
  if (!storage || !isScrollPosition(scrollTop)) return

  const positions = loadPositions(storage) ?? {
    version: PROXY_SCROLL_POSITIONS_SCHEMA_VERSION,
  }
  const legacyKey = legacyKeyFor(scrollPositionKey)
  if (legacyKey) delete positions[legacyKey]
  positions[scrollPositionKey] = scrollTop
  positions.version = PROXY_SCROLL_POSITIONS_SCHEMA_VERSION
  persistPositions(storage, positions)
}
