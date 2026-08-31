import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getProxyScrollPosition,
  PROXY_SCROLL_POSITIONS_KEY,
  PROXY_SCROLL_POSITIONS_SCHEMA_VERSION,
  saveProxyScrollPosition,
} from './proxy-scroll-positions'

const createStorage = () => {
  const values = new Map<string, string>()
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => values.set(key, value)),
    removeItem: vi.fn((key: string) => values.delete(key)),
  } as unknown as Storage
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('proxy scroll position storage', () => {
  it('migrates v2.4.7 rule and global positions in place', () => {
    const storage = createStorage()
    storage.setItem(
      PROXY_SCROLL_POSITIONS_KEY,
      JSON.stringify({ rule: 120, global: 240 }),
    )

    expect(getProxyScrollPosition('rule:normal', storage)).toBe(120)
    expect(JSON.parse(storage.getItem(PROXY_SCROLL_POSITIONS_KEY) ?? '')).toEqual(
      {
        version: PROXY_SCROLL_POSITIONS_SCHEMA_VERSION,
        'rule:normal': 120,
        'global:normal': 240,
      },
    )
    expect(getProxyScrollPosition('global:normal', storage)).toBe(240)
  })

  it('accepts existing new keys and adds an explicit schema version', () => {
    const storage = createStorage()
    storage.setItem(
      PROXY_SCROLL_POSITIONS_KEY,
      JSON.stringify({ 'rule:normal': 80 }),
    )

    expect(getProxyScrollPosition('rule:normal', storage)).toBe(80)
    expect(JSON.parse(storage.getItem(PROXY_SCROLL_POSITIONS_KEY) ?? '')).toEqual(
      { version: PROXY_SCROLL_POSITIONS_SCHEMA_VERSION, 'rule:normal': 80 },
    )
  })

  it('drops unknown schema versions and malformed stored values', () => {
    const storage = createStorage()
    storage.setItem(
      PROXY_SCROLL_POSITIONS_KEY,
      JSON.stringify({ version: PROXY_SCROLL_POSITIONS_SCHEMA_VERSION + 1 }),
    )
    expect(getProxyScrollPosition('rule:normal', storage)).toBeUndefined()
    expect(storage.getItem(PROXY_SCROLL_POSITIONS_KEY)).toBeNull()

    storage.setItem(PROXY_SCROLL_POSITIONS_KEY, 'not-json')
    expect(getProxyScrollPosition('global:normal', storage)).toBeUndefined()
    expect(storage.getItem(PROXY_SCROLL_POSITIONS_KEY)).toBeNull()
  })

  it('removes legacy fields when writing a migrated key', () => {
    const storage = createStorage()
    storage.setItem(
      PROXY_SCROLL_POSITIONS_KEY,
      JSON.stringify({ version: PROXY_SCROLL_POSITIONS_SCHEMA_VERSION, rule: 120 }),
    )

    saveProxyScrollPosition('rule:normal', 300, storage)
    expect(JSON.parse(storage.getItem(PROXY_SCROLL_POSITIONS_KEY) ?? '')).toEqual(
      {
        version: PROXY_SCROLL_POSITIONS_SCHEMA_VERSION,
        'rule:normal': 300,
      },
    )
  })

  it('treats a throwing localStorage getter as unavailable', () => {
    vi.spyOn(globalThis, 'localStorage', 'get').mockImplementation(() => {
      throw new Error('storage is unavailable')
    })

    expect(getProxyScrollPosition('rule:normal')).toBeUndefined()
    expect(() => saveProxyScrollPosition('rule:normal', 300)).not.toThrow()
  })
})
