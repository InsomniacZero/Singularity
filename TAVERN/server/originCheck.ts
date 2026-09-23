/**
 * Cross-site guard for the API (no auth otherwise — see README threat model: local-only).
 * Allows any loopback origin (any port), rejects any other Origin, and passes requests
 * with no Origin at all (curl, same-origin requests that omit it).
 */

import type { RequestHandler } from 'express'

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

function isLocalOrPrivateHost(hostname: string): boolean {
  if (LOOPBACK_HOSTS.has(hostname)) return true
  // Allow all standard private IPv4 ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x, 100.64-127.x.x)
  if (/^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.)/.test(hostname)) return true
  // Allow .local mDNS hostnames
  if (hostname.endsWith('.local')) return true
  return false
}

/**
 * Extra origins to accept beyond loopback, for a deployment reached over a network — Docker on a
 * home server, a reverse proxy, another device on the LAN. Set `RP_ALLOWED_ORIGINS` to a
 * comma-separated list (`http://192.168.1.9:8080,https://rp.example.com`); a single `*` turns the
 * check off entirely, which only makes sense when something in front is doing auth. Read fresh
 * each call so tests (and a restart-free env change) take effect.
 */
function extraAllowedOrigins(): string[] {
  return (process.env.RP_ALLOWED_ORIGINS ?? '')
    .split(',')
    .map((s) => s.trim().replace(/\/+$/, ''))
    .filter(Boolean)
}

export function originAllowed(origin: string | undefined): boolean {
  if (!origin) return true
  const extra = extraAllowedOrigins()
  if (extra.includes('*')) return true
  let url: URL
  try {
    url = new URL(origin)
  } catch {
    return false
  }
  if (isLocalOrPrivateHost(url.hostname)) return true
  return extra.includes(url.origin)
}

function headerValue(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v
}

/** Express middleware wrapping originAllowed; falls back to Referer only when Origin is absent. */
export const originGuard: RequestHandler = (req, res, next) => {
  const origin = headerValue(req.headers.origin)
  if (!originAllowed(origin)) {
    res.status(403).json({ error: 'Forbidden origin' })
    return
  }
  const referer = headerValue(req.headers.referer)
  if (!origin && referer) {
    try {
      if (!originAllowed(new URL(referer).origin)) {
        res.status(403).json({ error: 'Forbidden origin' })
        return
      }
    } catch {
      // Malformed Referer — ignore.
    }
  }
  next()
}
