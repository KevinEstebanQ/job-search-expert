const styles = {
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '48px',
    padding: '3px 8px',
    borderRadius: '3px',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    fontWeight: '700',
    letterSpacing: '0.02em',
    border: '1px solid',
    flexShrink: 0,
  },
}

function getScoreStyle(score) {
  if (score == null) return {
    color: 'var(--text-dim)',
    background: 'transparent',
    borderColor: 'var(--border)',
    boxShadow: 'none',
  }
  if (score >= 0.8) return {
    color: 'var(--score-high)',
    background: 'var(--score-high-bg)',
    borderColor: 'rgba(74, 222, 128, 0.3)',
    boxShadow: '0 0 8px var(--score-high-glow)',
  }
  if (score >= 0.65) return {
    color: 'var(--score-mid)',
    background: 'var(--score-mid-bg)',
    borderColor: 'rgba(251, 191, 36, 0.3)',
    boxShadow: '0 0 8px var(--score-mid-glow)',
  }
  return {
    color: 'var(--score-low)',
    background: 'var(--score-low-bg)',
    borderColor: 'rgba(82, 82, 91, 0.3)',
    boxShadow: 'none',
  }
}

export function scoreBorderColor(score) {
  if (score == null)  return 'var(--border)'
  if (score >= 0.8)   return 'var(--score-high)'
  if (score >= 0.65)  return 'var(--score-mid)'
  return 'var(--border)'
}

export default function ScoreBadge({ score, size = 'md' }) {
  const scoreStyle = getScoreStyle(score)
  const fontSize = size === 'lg' ? '15px' : '13px'

  return (
    <span style={{ ...styles.badge, ...scoreStyle, fontSize }}>
      {score != null ? score.toFixed(2) : '—'}
    </span>
  )
}
