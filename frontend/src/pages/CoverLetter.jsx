import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getJob, getAiStatus, draftCoverLetter, saveCoverLetter } from '../api/client'
import ScoreBadge from '../components/ScoreBadge'

export default function CoverLetter() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [aiAvailable, setAiAvailable] = useState(null)
  const [text, setText] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [saveState, setSaveState] = useState('idle') // idle | saving | saved
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [jobData, statusData] = await Promise.all([
          getJob(jobId),
          getAiStatus(),
        ])
        setJob(jobData)
        setAiAvailable(statusData.available)
        if (jobData.cover_letter) setText(jobData.cover_letter)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [jobId])

  async function handleGenerate() {
    if (!aiAvailable || streaming) return
    setText('')
    setStreaming(true)
    setError(null)
    setSaveState('idle')
    try {
      for await (const event of draftCoverLetter(jobId)) {
        if (event.error) { setError(event.error); break }
        if (event.chunk) setText(prev => prev + event.chunk)
        if (event.done) break
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setStreaming(false)
    }
  }

  async function handleSave() {
    if (!job?.app_id || !text) return
    setSaveState('saving')
    try {
      await saveCoverLetter(job.app_id, text)
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2500)
    } catch (e) {
      setError(e.message)
      setSaveState('idle')
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '48px 24px', fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
        loading...
      </div>
    )
  }

  if (!job) {
    return (
      <div style={{ padding: '48px 24px', fontFamily: 'var(--font-mono)', fontSize: '13px', color: '#ef4444' }}>
        {error || 'Job not found.'}
      </div>
    )
  }

  const hasApp = Boolean(job.app_id)

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 24px' }}>

      {/* Breadcrumb */}
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Link
          to="/pipeline"
          style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)', borderBottom: '1px solid var(--border)' }}
          onMouseEnter={e => { e.target.style.color = 'var(--accent)'; e.target.style.borderColor = 'var(--accent)' }}
          onMouseLeave={e => { e.target.style.color = 'var(--text-dim)'; e.target.style.borderColor = 'var(--border)' }}
        >
          ← Pipeline
        </Link>
        <span style={{ color: 'var(--text-dim)', fontSize: '12px' }}>/</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)' }}>
          cover letter
        </span>
      </div>

      {/* Job header */}
      <div style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '16px 20px',
        marginBottom: '24px',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        flexWrap: 'wrap',
      }}>
        <ScoreBadge score={job.score} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '18px', fontWeight: 700 }}>
            {job.title}
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '2px' }}>
            {job.company}
            {job.location && <span style={{ color: 'var(--text-dim)' }}> · {job.location}</span>}
          </div>
        </div>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', borderBottom: '1px solid var(--accent-glow)', paddingBottom: '1px', flexShrink: 0 }}
        >
          view posting →
        </a>
      </div>

      {/* Main layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px', alignItems: 'flex-start' }}>

        {/* Left: controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span className="section-title" style={{ fontSize: '11px' }}>AI Draft</span>

            {aiAvailable === false && (
              <div style={{
                padding: '12px',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--text-dim)',
                lineHeight: 1.5,
              }}>
                AI drafting requires <code style={{ color: 'var(--accent)' }}>ANTHROPIC_API_KEY</code> in your <code>.env</code>.
              </div>
            )}

            {aiAvailable && (
              <button
                className="btn btn-accent"
                onClick={handleGenerate}
                disabled={streaming}
                style={{ justifyContent: 'center' }}
              >
                {streaming ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>◌</span>
                    Generating...
                  </span>
                ) : text ? 'Regenerate Draft' : 'Generate Draft'}
              </button>
            )}
          </div>

          {/* Save */}
          {text && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span className="section-title" style={{ fontSize: '11px' }}>Save</span>
              {!hasApp && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-dim)' }}>
                  Mark job as Interested first to save.
                </div>
              )}
              <button
                className="btn"
                onClick={handleSave}
                disabled={!hasApp || saveState === 'saving' || streaming}
                style={{
                  justifyContent: 'center',
                  borderColor: saveState === 'saved' ? 'var(--score-high)' : undefined,
                  color: saveState === 'saved' ? 'var(--score-high)' : undefined,
                }}
              >
                {saveState === 'saving' ? 'Saving...' : saveState === 'saved' ? '✓ Saved' : 'Save to Pipeline'}
              </button>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{
              padding: '10px 12px',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 'var(--radius)',
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: '#ef4444',
            }}>
              {error}
            </div>
          )}

          {/* Format guide */}
          {text && !streaming && (
            <div style={{
              padding: '12px',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius)',
              fontSize: '11px',
              color: 'var(--text-dim)',
              lineHeight: 1.6,
            }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '11px', letterSpacing: '0.06em', marginBottom: '6px', color: 'var(--text-muted)' }}>
                OUTPUT SECTIONS
              </div>
              <div>— COVER LETTER —</div>
              <div>— RESUME BULLETS —</div>
              <div>— RED FLAGS —</div>
            </div>
          )}
        </div>

        {/* Right: textarea */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="section-title" style={{ fontSize: '11px' }}>Draft</span>
            {streaming && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--accent)', animation: 'pulse 1s infinite' }}>
                streaming...
              </span>
            )}
            {text && !streaming && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-dim)', marginLeft: 'auto' }}>
                {text.length} chars
              </span>
            )}
          </div>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            disabled={streaming}
            placeholder={
              aiAvailable
                ? 'Click "Generate Draft" to create a tailored cover letter...'
                : 'Add your cover letter here — or configure ANTHROPIC_API_KEY for AI drafting.'
            }
            style={{
              width: '100%',
              minHeight: '520px',
              padding: '16px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              color: streaming ? 'var(--text-muted)' : 'var(--text)',
              fontFamily: 'var(--font-body)',
              fontSize: '13px',
              lineHeight: 1.7,
              outline: 'none',
              resize: 'vertical',
              transition: 'border-color 0.15s',
            }}
            onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
          />
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  )
}
