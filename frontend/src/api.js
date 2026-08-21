async function req(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (r.status === 204) return null
  const data = await r.json().catch(() => null)
  if (!r.ok) {
    const msg = data?.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : r.statusText
    throw new Error(msg)
  }
  return data
}

export const api = {
  get: (u) => req('GET', u),
  post: (u, b = {}) => req('POST', u, b),
  put: (u, b) => req('PUT', u, b),
  patch: (u, b) => req('PATCH', u, b),
  del: (u) => req('DELETE', u),
}

export function fmtDate(v) {
  if (!v) return '—'
  const d = new Date(v)
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
export function fmtG(v, digits = 0) {
  if (v === null || v === undefined) return '—'
  return `${Number(v).toFixed(digits)} g`
}
export function locationLabel(loc) {
  if (!loc) return '—'
  if (loc.startsWith('ams:')) return `AMS A${Number(loc.slice(4)) + 1}`
  return loc.charAt(0).toUpperCase() + loc.slice(1)
}
export function levelClass(pct, th = { low_pct: 20 }) {
  if (pct <= 10) return 'fail'
  if (pct <= th.low_pct) return 'warn'
  return ''
}
