import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildWebdavSignature,
  clearWebdavStatus,
  getWebdavStatus,
  setWebdavStatus,
  WEBDAV_STATUS_KEY,
  WEBDAV_STATUS_SCHEMA_VERSION,
  WEBDAV_STATUS_TTL_MS,
} from './webdav-status'

const NOW = 1_700_000_000_000

const createStorage = () => {
  const values = new Map<string, string>()
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => values.set(key, value)),
    removeItem: vi.fn((key: string) => values.delete(key)),
  } as unknown as Storage
}

const config = {
  webdav_url: 'https://dav.example.test/backup',
  webdav_username: 'alice',
  webdav_password: 'do-not-store-this',
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('WebDAV status storage', () => {
  it('uses an endpoint and username identity without persisting the password', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    vi.spyOn(Date, 'now').mockReturnValue(NOW)

    const signature = buildWebdavSignature(config)
    setWebdavStatus(signature, 'ready')

    const raw = storage.getItem(WEBDAV_STATUS_KEY) ?? ''
    const payload = JSON.parse(raw) as Record<string, unknown>
    expect(signature).toBe(
      JSON.stringify([config.webdav_url, config.webdav_username]),
    )
    expect(raw).not.toContain(config.webdav_password)
    expect(payload.version).toBe(WEBDAV_STATUS_SCHEMA_VERSION)
    expect(payload.updatedAt).toBe(NOW)
    expect(getWebdavStatus(signature)).toBe('ready')
  })

  it('removes expired status instead of returning stale state', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    const signature = buildWebdavSignature(config)

    storage.setItem(
      WEBDAV_STATUS_KEY,
      JSON.stringify({
        version: WEBDAV_STATUS_SCHEMA_VERSION,
        signature,
        status: 'ready',
        updatedAt: NOW - WEBDAV_STATUS_TTL_MS - 1,
      }),
    )

    expect(getWebdavStatus(signature)).toBe('unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
  })

  it('clears legacy password-bearing entries without migrating them', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    const signature = buildWebdavSignature(config)
    const legacySignature = JSON.stringify([
      config.webdav_url,
      config.webdav_username,
      config.webdav_password,
    ])

    storage.setItem(
      WEBDAV_STATUS_KEY,
      JSON.stringify({
        signature: legacySignature,
        status: 'ready',
        updatedAt: NOW,
      }),
    )

    expect(getWebdavStatus(signature)).toBe('unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
  })

  it('clears password-bearing fields even when the signature is current', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    const signature = buildWebdavSignature(config)

    storage.setItem(
      WEBDAV_STATUS_KEY,
      JSON.stringify({
        version: WEBDAV_STATUS_SCHEMA_VERSION,
        signature,
        status: 'ready',
        updatedAt: NOW,
        password: config.webdav_password,
      }),
    )

    expect(getWebdavStatus(signature)).toBe('unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
  })

  it('clears unknown schema versions and explicit invalidation', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    const signature = buildWebdavSignature(config)

    storage.setItem(
      WEBDAV_STATUS_KEY,
      JSON.stringify({
        version: WEBDAV_STATUS_SCHEMA_VERSION + 1,
        signature,
        status: 'ready',
        updatedAt: NOW,
      }),
    )
    expect(getWebdavStatus(signature)).toBe('unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()

    setWebdavStatus(signature, 'ready')
    clearWebdavStatus()
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
  })

  it('removes status for an empty configuration or explicit unknown state', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    const signature = buildWebdavSignature(config)

    setWebdavStatus(signature, 'ready')
    expect(getWebdavStatus('')).toBe('unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()

    setWebdavStatus(signature, 'ready')
    setWebdavStatus(signature, 'unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
    expect(
      buildWebdavSignature({ webdav_password: config.webdav_password }),
    ).toBe('')
  })

  it('clears an empty stored value as corrupted data', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    const signature = buildWebdavSignature(config)

    storage.setItem(WEBDAV_STATUS_KEY, '')

    expect(getWebdavStatus(signature)).toBe('unknown')
    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
  })

  it('does not write a legacy password-bearing signature', () => {
    const storage = createStorage()
    vi.stubGlobal('localStorage', storage)
    const legacySignature = JSON.stringify([
      config.webdav_url,
      config.webdav_username,
      config.webdav_password,
    ])

    setWebdavStatus(legacySignature, 'ready')

    expect(storage.getItem(WEBDAV_STATUS_KEY)).toBeNull()
  })

  it('treats a throwing localStorage getter as unavailable', () => {
    const signature = buildWebdavSignature(config)
    vi.spyOn(globalThis, 'localStorage', 'get').mockImplementation(() => {
      throw new Error('storage is unavailable')
    })

    expect(getWebdavStatus(signature)).toBe('unknown')
    expect(() => clearWebdavStatus()).not.toThrow()
    expect(() => setWebdavStatus(signature, 'ready')).not.toThrow()
  })
})
