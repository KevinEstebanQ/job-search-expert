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

export function getApplications() {
  return req('/api/applications')
}

export function getApplication(id) {
  return req(`/api/applications/${id}`)
}

export function updateApplication(id, body) {
  return req(`/api/applications/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function saveCoverLetter(id, text) {
  return req(`/api/applications/${id}/cover-letter`, {
    method: 'PUT',
    body: JSON.stringify({ cover_letter: text }),
  })
}

export function getAiStatus() {
  return req('/api/ai/status')
}

export function getProfile() {
  return req('/api/profile')
}

export function saveProfile(body) {
  return req('/api/profile', { method: 'PUT', body: JSON.stringify(body) })
}

// Async generator — yields {chunk} events then a final {done: true}
export async function* draftCoverLetter(jobId) {
  const BASE = import.meta.env.VITE_API_BASE ?? ''
  const res = await fetch(`${BASE}/api/ai/draft/${jobId}`, { method: 'POST' })
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${msg}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        yield JSON.parse(line.slice(6))
      } catch { /* skip malformed */ }
    }
  }
}
