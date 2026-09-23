import { describe, it, expect } from 'vitest'
import { buildZip } from './zip'

describe('buildZip', () => {
  it('creates a valid zip blob with entries', async () => {
    const textEncoder = new TextEncoder()
    const blob = buildZip([
      { name: 'happy.png', bytes: textEncoder.encode('fake-png-data-happy') },
      { name: 'sad.png', bytes: textEncoder.encode('fake-png-data-sad') },
    ])
    expect(blob).toBeInstanceOf(Blob)
    expect(blob.type).toBe('application/zip')
    expect(blob.size).toBeGreaterThan(50)

    const arrayBuf = await blob.arrayBuffer()
    const uint8 = new Uint8Array(arrayBuf)
    // Check PK zip signature at start: 0x50, 0x4b, 0x03, 0x04
    expect(uint8[0]).toBe(0x50)
    expect(uint8[1]).toBe(0x4b)
    expect(uint8[2]).toBe(0x03)
    expect(uint8[3]).toBe(0x04)
  })

  it('converts base64 dataUrl into binary correctly', async () => {
    // 1x1 transparent PNG in base64
    const dataUrl = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
    const blob = buildZip([
      { name: 'transparent.png', dataUrl },
    ])
    expect(blob.size).toBeGreaterThan(60)
  })
})
