import { useState, useEffect, useCallback } from 'react'
import { getReviewQueue, markJobReviewed, markInterested, skipJob } from '../api/client'

const REASON_LABELS = {
  no_description: 'No Description',
  no_salary:      'No Salary',
  no_remote_type: 'No Remote Type',
  no_title_signal: 'No Title Signal',
}

const REASON_COLORS = {
  no_description:  '#ef4444',
  no_salary:       '#f59e0b',
  no_remote_type:  '#60a5fa',
  no_title_signal: '#a78bfa',
}

function ReasonPill({ reason }) {
  const label = REASON_LABELS[reason] || reason
  const color = REASON_COLORS[reason] || 'var(--text-dim)'
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '2px 8px',
      borderRadius: '999px',
      border: `1px solid ${color}`,
      color,
      fontFamily: 'var(--font-mono)',
      fontSize: '10px',
      fontWeight: 600,
      letterSpacing: '0.04em',
    }}>
      {label}
    </span>
  )
}

function ReviewCard({ job, onReviewed, onInterested, onSkip }) {
  const [busy, setBusy] = useState(false)
  const reasons = Array.isArray(job.review_reasons) ? job.review_reasons : []
  const score = job.score != null ? Math.round(job.score * 100) : null

  async function act(fn) {
    setBusy(true)
    try { await fn() } catch (e) { console.error(e) } finally { setBusy(false) }
  }

  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderLeft: '3px solid #f59e0b',
      borderRadius: 'var(--radius-lg)',
      padding: '14px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text)', marginBottom: '2px' }}>
            {job.title}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {job.company}
            {job.location && <span style={{ color: 'var(--text-dim)' }}> · {job.location}</span>}
          </div>
        </div>
        {score != null && (
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            fontWeight: 700,
            color: score >= 65 ? 'var(--score-high)' : score >= 40 ? 'var(--score-mid)' : 'var(--text-dim)',
            flexShrink: 0,
          }}>
            {score}
          </span>
        )}
      </div>

      {/* Reason pills */}
      {reasons.length > 0 && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {reasons.map(r => <ReasonPill key={r} reason={r} />)}
        </div>
      )}

      {/* Description preview */}
      {job.description_raw ? (
        <div style={{
          fontSize: '12px',
          color: 'var(--text-muted)',
          lineHeight: 1.5,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
        }}>
          {job.description_raw.replace(/<[^>]+>/g, ' ').trim()}
        </div>
      ) : (
        <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontStyle: 'italic' }}>
          No description available — manual review required.
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', paddingTop: '4px', borderTop: '1px solid var(--border-subtle)', flexWrap: 'wrap' }}>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', borderBottom: '1px solid var(--accent-glow)', paddingBottom: '1px' }}
        >
          view →
        </a>
        <div style={{ flex: 1 }} />
        <button
          className="btn"
          disabled={busy}
          onClick={() => act(() => onSkip(job.id))}
          style={{ fontSize: '11px' }}
        >
          Skip
        </button>
        <button
          className="btn"
          disabled={busy}
          onClick={() => act(() => onReviewed(job.id))}
          style={{ fontSize: '11px' }}
        >
          Mark Reviewed
        </button>
        <button
          className="btn btn-accent"
          disabled={busy}
          onClick={() => act(() => onInterested(job.id))}
          style={{ fontSize: '11px' }}
        >
          Interested
        </button>
      </div>
    </div>
  )
}

export default function ReviewQueue() {
  const [jobs, setJobs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchQueue = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getReviewQueue({ limit: 200 })
      setJobs(data.jobs || [])
      setTotal(data.total || 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchQueue() }, [fetchQueue])

  async function handleReviewed(id) {
    await markJobReviewed(id)
    setJobs(prev => prev.filter(j => j.id !== id))
    setTotal(prev => Math.max(0, prev - 1))
  }

  async function handleInterested(id) {
    await markInterested(id)
    await markJobReviewed(id)
    setJobs(prev => prev.filter(j => j.id !== id))
    setTotal(prev => Math.max(0, prev - 1))
  }

  async function handleSkip(id) {
    await skipJob(id)
    await markJobReviewed(id)
    setJobs(prev => prev.filter(j => j.id !== id))
    setTotal(prev => Math.max(0, prev - 1))
  }

  return (
    <div style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px', marginBottom: '8px' }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '32px', fontWeight: 700, letterSpacing: '0.02em' }}>
          REVIEW QUEUE
        </h1>
        {total > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
            {total} flagged
          </span>
        )}
      </div>
      <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '24px', lineHeight: 1.5 }}>
        Jobs flagged because key fields could not be parsed. Score may be unreliable — inspect each manually before deciding.
      </p>

      {loading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
          loading review queue...
        </div>
      )}

      {error && (
        <div style={{ color: '#ef4444', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
          error: {error}
        </div>
      )}

      {!loading && !error && jobs.length === 0 && (
        <div style={{
          padding: '48px',
          textAlign: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: '13px',
          color: 'var(--text-dim)',
          border: '1px dashed var(--border)',
          borderRadius: 'var(--radius-lg)',
        }}>
          No jobs flagged for review — queue is clear.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {jobs.map(job => (
          <ReviewCard
            key={job.id}
            job={job}
            onReviewed={handleReviewed}
            onInterested={handleInterested}
            onSkip={handleSkip}
          />
        ))}
      </div>
    </div>
  )
}
