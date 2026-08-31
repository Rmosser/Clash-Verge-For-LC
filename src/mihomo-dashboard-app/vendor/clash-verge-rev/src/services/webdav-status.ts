export type WebdavStatus = 'unknown' | 'ready' | 'failed'

export const WEBDAV_STATUS_KEY = 'webdav_status_cache'
export const WEBDAV_STATUS_SCHEMA_VERSION = 1
export const WEBDAV_STATUS_TTL_MS = 5 * 60 * 1000

interface WebdavStatusCache {
  version: typeof WEBDAV_STATUS_SCHEMA_VERSION
  signature: string
  status: Exclude<WebdavStatus, 'unknown'>
  updatedAt: number
}

export const buildWebdavSignature = (
  verge?: Pick<
    IVergeConfig,
    'webdav_url' | 'webdav_username' | 'webdav_password'
  > | null,
) => {
  const url = verge?.webdav_url?.trim() ?? ''
  const username = verge?.webdav_username?.trim() ?? ''

  if (!url || !username) return ''

  return JSON.stringify([url, username])
}

const isPasswordFreeSignature = (value: unknown): value is string => {
  if (typeof value !== 'string') return false

  try {
    const parts: unknown = JSON.parse(value)
    return (
      Array.isArray(parts) &&
      parts.length === 2 &&
      parts.every((part) => typeof part === 'string')
    )
  } catch {
    return false
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isWebdavStatusCache = (value: unknown): value is WebdavStatusCache => {
  if (!isRecord(value)) return false

  const keys = Object.keys(value)
  if (
    keys.length !== 4 ||
    !['version', 'signature', 'status', 'updatedAt'].every((key) =>
      keys.includes(key),
    )
  ) {
    return false
  }

  return (
    value.version === WEBDAV_STATUS_SCHEMA_VERSION &&
    isPasswordFreeSignature(value.signature) &&
    (value.status === 'ready' || value.status === 'failed') &&
    typeof value.updatedAt === 'number'
  )
}

const isValidTimestamp = (value: unknown, now: number) =>
  typeof value === 'number' &&
  Number.isInteger(value) &&
  Number.isFinite(value) &&
  value > 0 &&
  value <= now &&
  now - value <= WEBDAV_STATUS_TTL_MS

const getStorage = (): Storage | null => {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

export const clearWebdavStatus = () => {
  const storage = getStorage()
  if (!storage) return

  try {
    storage.removeItem(WEBDAV_STATUS_KEY)
  } catch {
    // Storage can be unavailable in private browsing or when quota is denied.
  }
}

export const getWebdavStatus = (signature: string): WebdavStatus => {
  if (!signature || !isPasswordFreeSignature(signature)) {
    clearWebdavStatus()
    return 'unknown'
  }
  const storage = getStorage()
  if (!storage) return 'unknown'

  let raw: string | null
  try {
    raw = storage.getItem(WEBDAV_STATUS_KEY)
  } catch {
    return 'unknown'
  }
  if (raw === null) return 'unknown'

  try {
    const data: unknown = JSON.parse(raw)
    if (!isWebdavStatusCache(data) || data.signature !== signature) {
      clearWebdavStatus()
      return 'unknown'
    }

    if (!isValidTimestamp(data.updatedAt, Date.now())) {
      clearWebdavStatus()
      return 'unknown'
    }

    return data.status
  } catch {
    clearWebdavStatus()
    return 'unknown'
  }
}

export const setWebdavStatus = (signature: string, status: WebdavStatus) => {
  if (!signature || !isPasswordFreeSignature(signature) || status === 'unknown') {
    clearWebdavStatus()
    return
  }
  const storage = getStorage()
  if (!storage) return

  const payload: WebdavStatusCache = {
    version: WEBDAV_STATUS_SCHEMA_VERSION,
    signature,
    status,
    updatedAt: Date.now(),
  }

  try {
    storage.setItem(WEBDAV_STATUS_KEY, JSON.stringify(payload))
  } catch {
    // Storage can be unavailable in private browsing or when quota is denied.
  }
}
