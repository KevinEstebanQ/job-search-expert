import { NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { getStats } from '../api/client'

const navStyle = {
  position: 'sticky',
  top: 0,
  zIndex: 100,
  background: 'rgba(13, 13, 16, 0.92)',
  backdropFilter: 'blur(8px)',
  borderBottom: '1px solid var(--border)',
  padding: '0 24px',
  display: 'flex',
  alignItems: 'center',
  gap: '32px',
  height: '52px',
}

const logoStyle = {
  fontFamily: 'var(--font-mono)',
  fontSize: '13px',
  fontWeight: 700,
  color: 'var(--accent)',
  letterSpacing: '0.04em',
  marginRight: '8px',
  flexShrink: 0,
}

const dividerStyle = {
  width: '1px',
  height: '20px',
  background: 'var(--border)',
}

const navLinkStyle = ({ isActive }) => ({
  fontFamily: 'var(--font-display)',
  fontSize: '13px',
  fontWeight: 600,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: isActive ? 'var(--text)' : 'var(--text-muted)',
  borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
  paddingBottom: '2px',
  transition: 'color 0.15s ease',
  display: 'flex',
  alignItems: 'center',
  gap: '5px',
})

export default function Nav() {
  const [reviewCount, setReviewCount] = useState(0)

  useEffect(() => {
    getStats()
      .then(d => setReviewCount(d.review_queue_flagged ?? 0))
      .catch(() => {})
    // Refresh every 60s
    const id = setInterval(() => {
      getStats()
        .then(d => setReviewCount(d.review_queue_flagged ?? 0))
        .catch(() => {})
    }, 60000)
    return () => clearInterval(id)
  }, [])

  return (
    <nav style={navStyle}>
      <span style={logoStyle}>job-search-expert</span>
      <div style={dividerStyle} />
      <NavLink to="/" end style={navLinkStyle}>Dashboard</NavLink>
      <NavLink to="/jobs" style={navLinkStyle}>Jobs</NavLink>
      <NavLink to="/pipeline" style={navLinkStyle}>Pipeline</NavLink>
      <NavLink to="/review" style={navLinkStyle}>
        Review
        {reviewCount > 0 && (
          <span style={{
            background: '#f59e0b',
            color: '#000',
            borderRadius: '999px',
            fontSize: '9px',
            fontWeight: 700,
            padding: '1px 5px',
            lineHeight: 1.4,
            letterSpacing: 0,
          }}>
            {reviewCount}
          </span>
        )}
      </NavLink>
      <NavLink to="/profile" style={navLinkStyle}>Profile</NavLink>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: 'var(--score-high)',
            boxShadow: '0 0 6px var(--score-high)',
            animation: 'pulse 2s ease-in-out infinite',
          }}
        />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--text-dim)',
          }}
        >
          api:8000
        </span>
      </div>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </nav>
  )
}
