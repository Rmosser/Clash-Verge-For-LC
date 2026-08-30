import { describe, expect, it } from 'vitest'

import { parseConnectionsPayload } from './use-connection-data'

const validConnection = {
  id: 'connection-1',
  metadata: {
    network: 'tcp',
    type: 'HTTP',
    host: 'example.test',
    sourceIP: '127.0.0.1',
    sourcePort: '12345',
    destinationPort: '443',
  },
  upload: 12,
  download: 34,
  start: '2026-08-31T00:00:00Z',
  chains: ['Proxy'],
  rule: 'MATCH',
  rulePayload: 'Proxy',
}

describe('Mihomo connections websocket payload parser', () => {
  it('accepts a complete snapshot', () => {
    expect(
      parseConnectionsPayload({
        uploadTotal: 12,
        downloadTotal: 34,
        connections: [validConnection],
      }),
    ).toEqual({
      uploadTotal: 12,
      downloadTotal: 34,
      connections: [validConnection],
    })
  })

  it('rejects malformed rows and non-finite counters before merging', () => {
    const snapshot = {
      uploadTotal: 12,
      downloadTotal: 34,
      connections: [validConnection],
    }

    expect(parseConnectionsPayload({ ...snapshot, connections: [null] })).toBeNull()
    expect(
      parseConnectionsPayload({
        ...snapshot,
        connections: [{ ...validConnection, metadata: null }],
      }),
    ).toBeNull()
    expect(parseConnectionsPayload({ ...snapshot, uploadTotal: Number.NaN })).toBeNull()
  })
})
