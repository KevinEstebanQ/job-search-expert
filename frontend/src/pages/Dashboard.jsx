import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { getStats, getJobs, triggerScrape, getScrapeStatus, getProfile } from '../api/client'
import JobCard from '../components/JobCard'
import ScoreBadge from '../components/ScoreBadge'

function StatCard({ label, value, accent }) {
  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '20px 22px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        flex: '1 1 160px',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: '42px',
          fontWeight: 700,
          lineHeight: 1,
          color: accent || 'var(--text)',
          letterSpacing: '-0.02em',
        }}
      >
        {value ?? '—'}
      </div>
      <div className="label">{label}</div>
    </div>
  )
}

function ScoutButton({ onComplete }) {
  const [state, setState] = useState('idle') // idle | running | done
  const [result, setResult] = useState(null)
  const pollRef = useRef(null)

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function run() {
    setState('running')
    setResult(null)
    try {
      await triggerScrape('all')
    } catch (e) {
      // already_running response comes back as 200, real errors abort here
      console.error(e)
      setState('idle')
      return
    }

    pollRef.current = setInterval(async () => {
      try {
        const status = await getScrapeStatus()
        if (!status.running) {
          stopPolling()
          setResult(status.last_result)
          setState('done')
          onComplete?.()
          setTimeout(() => setState('idle'), 8000)
        }
      } catch (e) {
        console.error('poll error', e)
        stopPolling()
        setState('idle')
      }
    }, 4000)
  }

  useEffect(() => () => stopPolling(), [])

  if (state === 'done' && result) {
    const total_new = result.results?.reduce((acc, r) => acc + (r.jobs_new || 0), 0) ?? 0
    const total_found = result.results?.reduce((acc, r) => acc + (r.jobs_found || 0), 0) ?? 0
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            color: 'var(--score-high)',
          }}
        >
          ✓ {total_found} scanned · {total_new} new · {result.jobs_scored} scored
        </span>
        <button className="btn btn-accent" onClick={run}>
          SCOUT AGAIN
        </button>
      </div>
    )
  }

  return (
    <button className="btn btn-accent" onClick={run} disabled={state === 'running'}>
      {state === 'running' ? (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>◌</span>
          SCANNING...
        </span>
      ) : (
        'RUN SCOUT'
      )}
    </button>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [picks, setPicks] = useState([])
  const [loading, setLoading] = useState(true)
  const [profileComplete, setProfileComplete] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const [statsData, jobsData, profileData] = await Promise.all([
        getStats(),
        getJobs({ score_min: 0.65, limit: 5, offset: 0 }),
        getProfile(),
      ])
      setStats(statsData)
      setProfileComplete(profileData.complete)
      // Top picks = highest scored with no application
      const unreviewed = jobsData.jobs.filter(j => !j.app_status).slice(0, 5)
      setPicks(unreviewed.length ? unreviewed : jobsData.jobs.slice(0, 5))
    } catch (e) {
      console.error('Dashboard fetch error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '32px 24px' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '32px',
        }}
      >
        <div>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '32px',
              fontWeight: 700,
              letterSpacing: '0.02em',
              color: 'var(--text)',
            }}
          >
            DASHBOARD
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Job search pipeline overview
          </p>
        </div>
        <ScoutButton onComplete={fetchData} />
      </div>

      {/* Onboarding banner */}
      {!profileComplete && !loading && (
        <div style={{
          marginBottom: '24px',
          padding: '14px 18px',
          background: 'var(--bg-elevated)',
          borderLeft: '3px solid var(--score-mid)',
          borderRadius: 'var(--radius)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: '12px', flexWrap: 'wrap',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)' }}>
            Profile not set up — jobs won't be scored accurately.
          </span>
          <Link
            to="/profile"
            style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--score-mid)', borderBottom: '1px solid var(--score-mid)', flexShrink: 0 }}
          >
            Set up your profile →
          </Link>
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '36px' }}>
        <StatCard label="Total Jobs" value={stats?.total_jobs?.toLocaleString()} />
        <StatCard
          label="Review Queue"
          value={stats?.review_queue}
          accent="var(--score-mid)"
        />
        <StatCard
          label="Unreviewed"
          value={stats?.unreviewed}
          accent="var(--accent)"
        />
        <StatCard
          label="Active Apps"
          value={stats?.active_applications}
          accent="var(--score-high)"
        />
        <StatCard label="New Today" value={stats?.new_today} />
      </div>

      {/* Top Picks */}
      <div className="section-header">
        <span className="section-title">Top Picks</span>
      </div>

      {loading ? (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            color: 'var(--text-dim)',
            padding: '32px 0',
          }}
        >
          loading...
        </div>
      ) : picks.length === 0 ? (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            color: 'var(--text-dim)',
            padding: '32px 0',
            lineHeight: 1.8,
          }}
        >
          {stats?.below_threshold > 0 ? (
            <>
              <span style={{ color: 'var(--score-mid)' }}>
                {stats.below_threshold} jobs found but all score below 0.65.
              </span>
              {' '}Check your profile — <span style={{ color: 'var(--accent)' }}>must_have skills</span> drive the score ceiling.
            </>
          ) : stats?.total_jobs === 0 ? (
            'No jobs in DB. Run Scout to discover jobs.'
          ) : (
            'No jobs in review queue (score ≥ 0.65). Run Scout to discover jobs.'
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {picks.map(job => (
            <JobCard key={job.id} job={job} onAction={fetchData} />
          ))}
          {stats?.review_queue > 5 && (
            <Link
              to="/jobs"
              style={{
                display: 'block',
                textAlign: 'center',
                padding: '12px',
                fontFamily: 'var(--font-display)',
                fontSize: '12px',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                marginTop: '4px',
              }}
              onMouseEnter={e => { e.target.style.color = 'var(--accent)'; e.target.style.borderColor = 'var(--accent)' }}
              onMouseLeave={e => { e.target.style.color = 'var(--text-muted)'; e.target.style.borderColor = 'var(--border)' }}
            >
              View all {stats.review_queue} jobs →
            </Link>
          )}
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
