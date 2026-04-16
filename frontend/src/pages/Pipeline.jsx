import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getApplications, updateApplication } from '../api/client'

const COLUMN_ORDER = [
  'interested', 'applied', 'phone_screen', 'interview', 'offer', 'rejected', 'withdrawn',
]

const COLUMN_LABELS = {
  interested:   'Interested',
  applied:      'Applied',
  phone_screen: 'Phone Screen',
  interview:    'Interview',
  offer:        'Offer',
  rejected:     'Rejected',
  withdrawn:    'Withdrawn',
}

const COLUMN_ACCENT = {
  interested:   'var(--accent)',
  applied:      '#60a5fa',
  phone_screen: '#a78bfa',
  interview:    '#34d399',
  offer:        'var(--score-high)',
  rejected:     '#ef4444',
  withdrawn:    'var(--text-dim)',
}

const SOURCE_LABELS = {
  greenhouse: 'GH', remoteok: 'ROK', dice: 'DICE',
  indeed: 'IND', wellfound: 'WF', linkedin: 'LI',
}

const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  background: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  color: 'var(--text)',
  fontFamily: 'var(--font-body)',
  fontSize: '13px',
  outline: 'none',
}

// ── App Card ─────────────────────────────────────────────────────────────────

function AppCard({ app, accent, onClick }) {
  const today = new Date().toISOString().slice(0, 10)
  const overdue = app.follow_up_date && app.follow_up_date < today

  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${accent}`,
        borderRadius: 'var(--radius-lg)',
        padding: '10px 12px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-surface)' }}
    >
      {/* Score + title */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
        {app.score != null && (
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            color: app.score >= 0.65
              ? 'var(--score-high)'
              : app.score >= 0.4
              ? 'var(--score-mid)'
              : 'var(--text-dim)',
            flexShrink: 0,
            paddingTop: '1px',
          }}>
            {Math.round(app.score * 100)}
          </span>
        )}
        <div style={{
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.3,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}>
          {app.title}
        </div>
      </div>

      {/* Company + chips */}
      <div style={{ display: 'flex', gap: '5px', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {app.company}
        </span>
        {app.source && (
          <span className="chip" style={{ fontSize: '10px', padding: '1px 5px' }}>
            {SOURCE_LABELS[app.source] || app.source}
          </span>
        )}
        {app.remote_type === 'remote' && (
          <span className="chip chip-remote" style={{ fontSize: '10px', padding: '1px 5px' }}>RMT</span>
        )}
      </div>

      {/* Follow-up indicator */}
      {app.follow_up_date && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: overdue ? '#ef4444' : 'var(--text-dim)',
        }}>
          {overdue ? '⚠ ' : '↩ '}{app.follow_up_date}
        </div>
      )}
    </div>
  )
}

// ── Detail Modal ──────────────────────────────────────────────────────────────

function AppModal({ app, onClose, onUpdate }) {
  const [status, setStatus] = useState(app.status)
  const [notes, setNotes] = useState(app.notes || '')
  const [followUp, setFollowUp] = useState(app.follow_up_date || '')
  const [contactName, setContactName] = useState(app.contact_name || '')
  const [contactEmail, setContactEmail] = useState(app.contact_email || '')
  const [saving, setSaving] = useState(false)
  const [statusSaving, setStatusSaving] = useState(false)

  async function handleStatusChange(newStatus) {
    if (newStatus === status) return
    setStatusSaving(true)
    try {
      await updateApplication(app.id, { status: newStatus })
      setStatus(newStatus)
      onUpdate()
    } catch (e) {
      console.error(e)
    } finally {
      setStatusSaving(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await updateApplication(app.id, {
        notes: notes || null,
        follow_up_date: followUp || null,
        contact_name: contactName || null,
        contact_email: contactEmail || null,
      })
      onUpdate()
      onClose()
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const accent = COLUMN_ACCENT[status] || 'var(--accent)'

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '24px',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        width: 'min(560px, 100%)',
        maxHeight: 'calc(100vh - 48px)',
        overflowY: 'auto',
        background: 'var(--bg-elevated)',
        border: `1px solid var(--border)`,
        borderTop: `3px solid ${accent}`,
        borderRadius: 'var(--radius-lg)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, lineHeight: 1.2 }}>
              {app.title}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {app.company}
              {app.location && <span style={{ color: 'var(--text-dim)' }}> · {app.location}</span>}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-dim)', fontSize: '18px', cursor: 'pointer', padding: '0 4px', flexShrink: 0 }}
            onMouseEnter={e => { e.target.style.color = 'var(--text)' }}
            onMouseLeave={e => { e.target.style.color = 'var(--text-dim)' }}
          >
            ✕
          </button>
        </div>

        {/* Status + meta */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={status}
            onChange={e => handleStatusChange(e.target.value)}
            disabled={statusSaving}
            style={{
              background: 'var(--bg-surface)',
              border: `1px solid ${accent}`,
              borderRadius: 'var(--radius)',
              color: accent,
              fontFamily: 'var(--font-display)',
              fontSize: '12px',
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              padding: '5px 10px',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {COLUMN_ORDER.map(s => (
              <option key={s} value={s} style={{ color: 'var(--text)', background: 'var(--bg-elevated)' }}>
                {COLUMN_LABELS[s]}
              </option>
            ))}
          </select>

          <a
            href={app.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', borderBottom: '1px solid var(--accent-glow)', paddingBottom: '1px' }}
          >
            view posting →
          </a>

          {app.score != null && (
            <span style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              color: app.score >= 0.65 ? 'var(--score-high)' : app.score >= 0.4 ? 'var(--score-mid)' : 'var(--text-dim)',
            }}>
              score {Math.round(app.score * 100)}
            </span>
          )}
        </div>

        {/* Editable fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <FieldGroup label="Notes">
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={4}
              placeholder="Interview notes, recruiter details, anything..."
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </FieldGroup>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <FieldGroup label="Contact Name">
              <input value={contactName} onChange={e => setContactName(e.target.value)} placeholder="Recruiter name" style={inputStyle} />
            </FieldGroup>
            <FieldGroup label="Contact Email">
              <input value={contactEmail} onChange={e => setContactEmail(e.target.value)} placeholder="hr@company.com" type="email" style={inputStyle} />
            </FieldGroup>
          </div>

          <FieldGroup label="Follow-up Date">
            <input value={followUp} onChange={e => setFollowUp(e.target.value)} type="date" style={{ ...inputStyle, colorScheme: 'dark' }} />
          </FieldGroup>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', paddingTop: '4px', borderTop: '1px solid var(--border-subtle)' }}>
          <Link
            to={`/cover-letter/${app.job_id}`}
            onClick={onClose}
            style={{
              padding: '6px 12px',
              fontFamily: 'var(--font-display)',
              fontSize: '12px',
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              background: 'var(--bg-elevated)',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              transition: 'all 0.15s',
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >
            Draft Letter
          </Link>
          <div style={{ flex: 1 }} />
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-accent" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FieldGroup({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <span className="label">{label}</span>
      {children}
    </div>
  )
}

// ── Pipeline Page ─────────────────────────────────────────────────────────────

export default function Pipeline() {
  const [grouped, setGrouped] = useState({})
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedApp, setSelectedApp] = useState(null)

  const fetchApps = useCallback(async () => {
    try {
      const data = await getApplications()
      setGrouped(data.applications || {})
      setTotal(data.total || 0)
    } catch (e) {
      console.error('Pipeline fetch error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchApps() }, [fetchApps])

  if (loading) {
    return (
      <div style={{ padding: '48px 24px', fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
        loading pipeline...
      </div>
    )
  }

  return (
    <div style={{ padding: '24px', height: 'calc(100vh - 52px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px', marginBottom: '20px', flexShrink: 0 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '32px', fontWeight: 700, letterSpacing: '0.02em' }}>
          PIPELINE
        </h1>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
          {total} tracked
        </span>
      </div>

      {/* Kanban board */}
      {total === 0 ? (
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--text-dim)',
          flexDirection: 'column', gap: '8px',
        }}>
          <div>No applications tracked yet.</div>
          <div style={{ fontSize: '11px' }}>Mark jobs as Interested from the Jobs page to start tracking.</div>
        </div>
      ) : (
        <div style={{
          display: 'flex',
          gap: '12px',
          overflowX: 'auto',
          overflowY: 'hidden',
          flex: 1,
          alignItems: 'flex-start',
          paddingBottom: '16px',
        }}>
          {COLUMN_ORDER.map(status => {
            const cards = grouped[status] || []
            const accent = COLUMN_ACCENT[status]

            return (
              <div key={status} style={{
                minWidth: '240px',
                maxWidth: '260px',
                flexShrink: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
                maxHeight: '100%',
              }}>
                {/* Column header */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  paddingBottom: '8px',
                  borderBottom: `2px solid ${accent}`,
                  marginBottom: '2px',
                  flexShrink: 0,
                }}>
                  <span style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: '13px',
                    fontWeight: 700,
                    letterSpacing: '0.1em',
                    textTransform: 'uppercase',
                    color: accent,
                  }}>
                    {COLUMN_LABELS[status]}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)', marginLeft: 'auto' }}>
                    {cards.length}
                  </span>
                </div>

                {/* Scrollable card list */}
                <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                  {cards.length === 0 ? (
                    <div style={{
                      padding: '16px 10px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      color: 'var(--text-dim)',
                      textAlign: 'center',
                      border: '1px dashed var(--border-subtle)',
                      borderRadius: 'var(--radius)',
                    }}>
                      empty
                    </div>
                  ) : (
                    cards.map(app => (
                      <AppCard
                        key={app.id}
                        app={app}
                        accent={accent}
                        onClick={() => setSelectedApp(app)}
                      />
                    ))
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Detail modal */}
      {selectedApp && (
        <AppModal
          app={selectedApp}
          onClose={() => setSelectedApp(null)}
          onUpdate={() => {
            fetchApps()
            setSelectedApp(null)
          }}
        />
      )}
    </div>
  )
}
