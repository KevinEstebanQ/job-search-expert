import { useState, useEffect, useCallback, useRef } from 'react'
import { getJobs, wipeJobs } from '../api/client'
import JobCard from '../components/JobCard'

const SOURCES = ['linkedin', 'indeed', 'glassdoor', 'zip_recruiter', 'dice', 'greenhouse', 'remoteok']
const SOURCE_LABELS = { linkedin: 'LinkedIn', indeed: 'Indeed', glassdoor: 'Glassdoor', zip_recruiter: 'ZipRecruiter', dice: 'Dice', greenhouse: 'Greenhouse', remoteok: 'RemoteOK' }
const SCORE_PRESETS = [
  { label: 'All', value: 0 },
  { label: '≥0.65', value: 0.65 },
  { label: '≥0.80', value: 0.80 },
]
const REMOTE_OPTS = ['remote', 'hybrid', 'onsite']
const PAGE_SIZE = 20

function FilterChip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 12px',
        fontFamily: 'var(--font-display)',
        fontSize: '12px',
        fontWeight: 600,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        borderRadius: 'var(--radius)',
        border: '1px solid',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        background: active ? 'var(--accent-dim)' : 'transparent',
        borderColor: active ? 'var(--accent)' : 'var(--border)',
        color: active ? 'var(--accent)' : 'var(--text-muted)',
      }}
    >
      {label}
    </button>
  )
}

export default function Jobs() {
  const [jobs, setJobs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(true)

  const [search, setSearch] = useState('')
  const [scoreMin, setScoreMin] = useState(0)
  const [source, setSource] = useState(null)
  const [remoteType, setRemoteType] = useState(null)

  const searchTimer = useRef(null)

  const filters = { score_min: scoreMin, source, remote_type: remoteType, search }

  const fetchJobs = useCallback(async (currentOffset, reset = false) => {
    setLoading(true)
    try {
      const data = await getJobs({ ...filters, limit: PAGE_SIZE, offset: currentOffset })
      const fetched = data.jobs || []
      setTotal(data.total ?? data.count ?? 0)
      setJobs(prev => reset ? fetched : [...prev, ...fetched])
      setHasMore(fetched.length === PAGE_SIZE)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [scoreMin, source, remoteType, search])

  // Reset + fetch on filter change
  useEffect(() => {
    setOffset(0)
    setJobs([])
    fetchJobs(0, true)
  }, [scoreMin, source, remoteType, search])

  function handleSearchChange(e) {
    clearTimeout(searchTimer.current)
    const val = e.target.value
    searchTimer.current = setTimeout(() => setSearch(val), 350)
  }

  function loadMore() {
    const next = offset + PAGE_SIZE
    setOffset(next)
    fetchJobs(next)
  }

  function toggleSource(s) { setSource(prev => prev === s ? null : s) }
  function toggleRemote(r) { setRemoteType(prev => prev === r ? null : r) }

  const [wipeInput, setWipeInput] = useState('')
  const [wiping, setWiping] = useState(false)
  const [wipeResult, setWipeResult] = useState(null)
  const wipeReady = wipeInput.trim().toLowerCase() === 'wipe'

  async function handleWipe() {
    if (!wipeReady || wiping) return
    setWiping(true)
    try {
      const result = await wipeJobs()
      setWipeResult(result)
      setWipeInput('')
      setOffset(0)
      setJobs([])
      fetchJobs(0, true)
    } catch (e) {
      console.error(e)
    } finally {
      setWiping(false)
    }
  }

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '32px 24px' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '32px',
              fontWeight: 700,
              letterSpacing: '0.02em',
            }}
          >
            JOBS
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
            {total > 0 ? (
              <span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{total}</span>
                {' '}matching jobs
              </span>
            ) : loading ? 'loading...' : 'No jobs found'}
          </p>
        </div>

        {/* Wipe control */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px' }}>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <input
              value={wipeInput}
              onChange={e => { setWipeInput(e.target.value); setWipeResult(null) }}
              placeholder='type "wipe" to confirm'
              style={{
                padding: '6px 10px',
                background: 'var(--bg-surface)',
                border: `1px solid ${wipeReady ? '#ef4444' : 'var(--border)'}`,
                borderRadius: 'var(--radius)',
                color: wipeReady ? '#ef4444' : 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                outline: 'none',
                width: '160px',
                transition: 'border-color 0.15s',
              }}
            />
            <button
              onClick={handleWipe}
              disabled={!wipeReady || wiping}
              style={{
                padding: '6px 12px',
                fontFamily: 'var(--font-display)',
                fontSize: '11px',
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                borderRadius: 'var(--radius)',
                border: '1px solid #ef4444',
                background: wipeReady ? 'rgba(239,68,68,0.12)' : 'transparent',
                color: wipeReady ? '#ef4444' : 'var(--text-dim)',
                cursor: wipeReady && !wiping ? 'pointer' : 'not-allowed',
                transition: 'all 0.15s',
              }}
            >
              {wiping ? 'Wiping...' : 'Wipe DB'}
            </button>
          </div>
          {wipeResult && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-dim)' }}>
              deleted {wipeResult.deleted} · preserved {wipeResult.preserved}
            </span>
          )}
        </div>
      </div>

      {/* Filter bar */}
      <div
        style={{
          position: 'sticky',
          top: '52px',
          zIndex: 50,
          background: 'rgba(13, 13, 16, 0.95)',
          backdropFilter: 'blur(8px)',
          padding: '14px 0',
          borderBottom: '1px solid var(--border-subtle)',
          marginBottom: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        {/* Search */}
        <input
          type="text"
          placeholder="Search title or company..."
          onChange={handleSearchChange}
          style={{
            width: '100%',
            padding: '9px 14px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            color: 'var(--text)',
            fontFamily: 'var(--font-body)',
            fontSize: '13px',
            outline: 'none',
            transition: 'border-color 0.15s ease',
          }}
          onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
          onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
        />

        {/* Filters row */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="label" style={{ marginRight: '4px' }}>Score</span>
          {SCORE_PRESETS.map(p => (
            <FilterChip
              key={p.label}
              label={p.label}
              active={scoreMin === p.value}
              onClick={() => setScoreMin(p.value)}
            />
          ))}

          <div style={{ width: '1px', height: '20px', background: 'var(--border)', margin: '0 4px' }} />
          <span className="label" style={{ marginRight: '4px' }}>Type</span>
          {REMOTE_OPTS.map(r => (
            <FilterChip
              key={r}
              label={r}
              active={remoteType === r}
              onClick={() => toggleRemote(r)}
            />
          ))}

          <div style={{ width: '1px', height: '20px', background: 'var(--border)', margin: '0 4px' }} />
          <span className="label" style={{ marginRight: '4px' }}>Source</span>
          {SOURCES.map(s => (
            <FilterChip
              key={s}
              label={SOURCE_LABELS[s]}
              active={source === s}
              onClick={() => toggleSource(s)}
            />
          ))}
        </div>
      </div>

      {/* Job list */}
      {jobs.length === 0 && !loading ? (
        <div
          style={{
            padding: '48px 0',
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            color: 'var(--text-dim)',
          }}
        >
          No jobs match the current filters.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {jobs.map(job => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}

      {/* Load more */}
      {hasMore && !loading && jobs.length > 0 && (
        <button
          className="btn"
          onClick={loadMore}
          style={{
            width: '100%',
            marginTop: '16px',
            justifyContent: 'center',
            padding: '10px',
          }}
        >
          Load more
        </button>
      )}

      {loading && (
        <div
          style={{
            padding: '24px 0',
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            color: 'var(--text-dim)',
          }}
        >
          loading...
        </div>
      )}
    </div>
  )
}
