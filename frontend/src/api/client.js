// In dev: VITE_API_BASE=http://localhost:8000 (set in .env.development)
// In Docker: VITE_API_BASE is unset → BASE is '' → nginx proxies /api/* to backend
const BASE = import.meta.env.VITE_API_BASE ?? ''

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${err}`)
  }
  return res.json()
}

export function getStats() {
  return req('/api/stats')
}

export function getJobs(filters = {}) {
  const params = new URLSearchParams()
  if (filters.score_min != null) params.set('score_min', filters.score_min)
  if (filters.score_max != null) params.set('score_max', filters.score_max)
  if (filters.source)           params.set('source', filters.source)
  if (filters.remote_type)      params.set('remote_type', filters.remote_type)
  if (filters.search)           params.set('search', filters.search)
  if (filters.limit != null)    params.set('limit', filters.limit)
  if (filters.offset != null)   params.set('offset', filters.offset)
  const qs = params.toString()
  return req(`/api/jobs${qs ? `?${qs}` : ''}`)
}

export function getJob(id) {
  return req(`/api/jobs/${id}`)
}

export function markInterested(id) {
  return req(`/api/jobs/${id}/interested`, { method: 'POST' })
}

export function skipJob(id) {
  return req(`/api/jobs/${id}/skip`, { method: 'POST' })
}

export function triggerScrape(source = 'all') {
  return req(`/api/scrape/${source}`, { method: 'POST' })
}

export function getScrapeLog() {
  return req('/api/scrape/log')
}
