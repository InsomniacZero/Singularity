/**
 * Lightweight, zero-dependency browser-compatible ZIP archive builder.
 * Packages PNG sprites directly into standard ZIP format (method 0 / stored,
 * which is optimal since PNG images are already pre-compressed).
 */

const CRC_TABLE = new Uint32Array(256)
for (let i = 0; i < 256; i++) {
  let c = i
  for (let j = 0; j < 8; j++) {
    c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  }
  CRC_TABLE[i] = c
}

function calculateCrc32(buf: Uint8Array): number {
  let crc = -1
  for (let i = 0; i < buf.length; i++) {
    crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ buf[i]) & 0xff]
  }
  return (crc ^ -1) >>> 0
}

function dataUrlToBytes(dataUrl: string): Uint8Array {
  const base64Index = dataUrl.indexOf(';base64,')
  const base64 = base64Index !== -1 ? dataUrl.slice(base64Index + 8) : dataUrl
  const binaryString = atob(base64)
  const bytes = new Uint8Array(binaryString.length)
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }
  return bytes
}

export interface ZipEntry {
  name: string
  dataUrl?: string
  bytes?: Uint8Array
}

export function buildZip(files: ZipEntry[]): Blob {
  const encoder = new TextEncoder()
  const localChunks: Uint8Array[] = []
  const cdChunks: Uint8Array[] = []
  let offset = 0

  for (const file of files) {
    const data = file.bytes ?? (file.dataUrl ? dataUrlToBytes(file.dataUrl) : new Uint8Array(0))
    const nameBytes = encoder.encode(file.name)
    const crc = calculateCrc32(data)
    const size = data.length

    // Local file header (30 bytes + filename)
    const lh = new Uint8Array(30 + nameBytes.length)
    const lv = new DataView(lh.buffer)
    lv.setUint32(0, 0x04034b50, true) // Signature
    lv.setUint16(4, 20, true)         // Version needed (2.0)
    lv.setUint16(6, 0, true)          // Flags
    lv.setUint16(8, 0, true)          // Compression method: 0 (Stored)
    lv.setUint16(10, 0, true)         // Mod time
    lv.setUint16(12, 0, true)         // Mod date
    lv.setUint32(14, crc, true)       // CRC-32
    lv.setUint32(18, size, true)      // Compressed size
    lv.setUint32(22, size, true)      // Uncompressed size
    lv.setUint16(26, nameBytes.length, true) // File name length
    lv.setUint16(28, 0, true)         // Extra field length
    lh.set(nameBytes, 30)

    localChunks.push(lh, data)

    // Central directory file header (46 bytes + filename)
    const cdh = new Uint8Array(46 + nameBytes.length)
    const cv = new DataView(cdh.buffer)
    cv.setUint32(0, 0x02014b50, true) // Central directory signature
    cv.setUint16(4, 20, true)         // Version made by
    cv.setUint16(6, 20, true)         // Version needed
    cv.setUint16(8, 0, true)          // Flags
    cv.setUint16(10, 0, true)         // Method (0)
    cv.setUint16(12, 0, true)         // Mod time
    cv.setUint16(14, 0, true)         // Mod date
    cv.setUint32(16, crc, true)       // CRC-32
    cv.setUint32(20, size, true)      // Compressed size
    cv.setUint32(24, size, true)      // Uncompressed size
    cv.setUint16(28, nameBytes.length, true) // Name length
    cv.setUint16(30, 0, true)         // Extra field length
    cv.setUint16(32, 0, true)         // Comment length
    cv.setUint16(34, 0, true)         // Disk number start
    cv.setUint16(36, 0, true)         // Internal file attributes
    cv.setUint32(38, 0, true)         // External file attributes
    cv.setUint32(42, offset, true)    // Relative offset of local header
    cdh.set(nameBytes, 46)

    cdChunks.push(cdh)
    offset += lh.length + size
  }

  const cdOffset = offset
  let cdSize = 0
  for (const c of cdChunks) {
    cdSize += c.length
  }

  // End of central directory record (22 bytes)
  const eocd = new Uint8Array(22)
  const ev = new DataView(eocd.buffer)
  ev.setUint32(0, 0x06054b50, true) // EOCD signature
  ev.setUint16(4, 0, true)          // Disk number
  ev.setUint16(6, 0, true)          // Disk with CD
  ev.setUint16(8, files.length, true)  // Disk entries
  ev.setUint16(10, files.length, true) // Total entries
  ev.setUint32(12, cdSize, true)    // Size of central directory
  ev.setUint32(16, cdOffset, true)  // Offset of central directory
  ev.setUint16(20, 0, true)         // Comment length

  return new Blob([...localChunks, ...cdChunks, eocd] as unknown as BlobPart[], { type: 'application/zip' })
}

export function downloadZip(filename: string, files: ZipEntry[]): void {
  const blob = buildZip(files)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.zip') ? filename : `${filename}.zip`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
