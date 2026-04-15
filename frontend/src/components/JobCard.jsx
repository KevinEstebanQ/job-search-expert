import { useState } from 'react'
import ScoreBadge, { scoreBorderColor } from './ScoreBadge'
import { markInterested, skipJob } from '../api/client'

const SOURCE_LABELS = {
  greenhouse: 'GH',
  remoteok:   'ROK',
  dice:       'DICE',
  indeed:     'IND',
  wellfound:  'WF',
  linkedin:   'LI',
}

function RemoteChip({ type }) {
  if (!type) return null
  const cls = type === 'remote' ? 'chip chip-remote' : type === 'hybrid' ? 'chip chip-hybrid' : 'chip chip-onsite'
  return <span className={cls}>{type.toUpperCase()}</span>
}

export default function JobCard({ job, onAction }) {
  const [status, setStatus] = useState(job.app_status || null)
  const [loading, setLoading] = useState(null)

  async function handleInterested() {
    setLoading('interested')
    try {
      await markInterested(job.id)
      setStatus('interested')
      onAction?.('interested', job.id)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(null)
    }
  }

  async function handleSkip() {
    setLoading('skip')
    try {
      await skipJob(job.id)
      setStatus('skipped')
      onAction?.('skip', job.id)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(null)
    }
  }

  const borderColor = scoreBorderColor(job.score)
  const isActioned = status === 'interested' || status === 'skipped'

  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${borderColor}`,
        borderRadius: 'var(--radius-lg)',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        opacity: status === 'skipped' ? 0.45 : 1,
        transition: 'opacity 0.2s ease, border-color 0.2s ease',
      }}
    >
      {/* Top row: score + title */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <ScoreBadge score={job.score} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--text)',
              lineHeight: 1.35,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={job.title}
          >
            {job.title}
          </div>
          <div
            style={{
              fontSize: '12px',
              color: 'var(--text-muted)',
              marginTop: '2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {job.company}
            {job.location && (
              <span style={{ color: 'var(--text-dim)', marginLeft: '6px' }}>
                · {job.location}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Meta chips */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
        {job.source && (
          <span className="chip">{SOURCE_LABELS[job.source] || job.source}</span>
        )}
        <RemoteChip type={job.remote_type} />
        {job.salary_min && (
          <span className="chip" style={{ fontFamily: 'var(--font-mono)' }}>
            ${Math.round(job.salary_min / 1000)}k
            {job.salary_max ? `–${Math.round(job.salary_max / 1000)}k` : '+'}
          </span>
        )}
        {job.date_posted && (
          <span
            style={{
              marginLeft: 'auto',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-dim)',
            }}
          >
            {job.date_posted}
          </span>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '2px' }}>
        {status === 'interested' ? (
          <span style={{ fontSize: '12px', color: 'var(--score-high)', fontFamily: 'var(--font-mono)' }}>
            ✓ interested
          </span>
        ) : status === 'skipped' ? (
          <span style={{ fontSize: '12px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            skipped
          </span>
        ) : (
          <>
            <button
              className="btn btn-interested"
              onClick={handleInterested}
              disabled={loading != null}
            >
              {loading === 'interested' ? '...' : '+ Interested'}
            </button>
            <button
              className="btn btn-skip"
              onClick={handleSkip}
              disabled={loading != null}
            >
              {loading === 'skip' ? '...' : 'Skip'}
            </button>
          </>
        )}
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            marginLeft: 'auto',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-dim)',
            borderBottom: '1px solid var(--border)',
            paddingBottom: '1px',
          }}
          onMouseEnter={e => { e.target.style.color = 'var(--accent)'; e.target.style.borderColor = 'var(--accent)' }}
          onMouseLeave={e => { e.target.style.color = 'var(--text-dim)'; e.target.style.borderColor = 'var(--border)' }}
        >
          view →
        </a>
      </div>
    </div>
  )
}
