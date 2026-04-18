import { useState, useEffect } from 'react'
import { getProfile, saveProfile } from '../api/client'

// ── Tag list (add on Enter, remove on ×) ──────────────────────────────────
function TagList({ label, values, onChange }) {
  const [input, setInput] = useState('')

  function addTag(e) {
    if ((e.key === 'Enter' || e.key === ',') && input.trim()) {
      e.preventDefault()
      const tag = input.trim().replace(/,$/, '')
      if (tag && !values.includes(tag)) onChange([...values, tag])
      setInput('')
    }
  }

  function remove(tag) {
    onChange(values.filter(v => v !== tag))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {label && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)' }}>{label}</span>}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: '6px',
        padding: '8px 10px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        minHeight: '38px',
        alignItems: 'center',
      }}>
        {values.map(tag => (
          <span key={tag} style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            padding: '2px 8px',
            background: 'var(--accent-dim)',
            border: '1px solid var(--accent-glow)',
            borderRadius: '3px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--accent)',
          }}>
            {tag}
            <button
              onClick={() => remove(tag)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: '0 0 0 2px', lineHeight: 1, fontSize: '12px' }}
            >×</button>
          </span>
        ))}
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={addTag}
          placeholder="type + Enter"
          style={{
            flex: '1 1 100px', minWidth: '80px',
            background: 'transparent', border: 'none', outline: 'none',
            fontFamily: 'var(--font-mono)', fontSize: '11px',
            color: 'var(--text)', padding: '0',
          }}
        />
      </div>
    </div>
  )
}

// ── Toggle row (label + checkbox) ─────────────────────────────────────────
function Toggle({ label, checked, onChange }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        style={{ accentColor: 'var(--accent)', width: '14px', height: '14px' }}
      />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)' }}>{label}</span>
    </label>
  )
}

// ── Number field ───────────────────────────────────────────────────────────
function NumberField({ label, value, onChange, placeholder, nullable }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)' }}>{label}</span>
      <input
        type="number"
        value={value ?? ''}
        onChange={e => {
          const v = e.target.value
          onChange(nullable && v === '' ? null : Number(v))
        }}
        placeholder={placeholder}
        style={{
          width: '120px', padding: '6px 10px',
          background: 'var(--bg-surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', color: 'var(--text)',
          fontFamily: 'var(--font-mono)', fontSize: '12px', outline: 'none',
        }}
        onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
        onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
      />
    </div>
  )
}

// ── Section wrapper ────────────────────────────────────────────────────────
function Section({ title, children }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: '20px',
      display: 'flex', flexDirection: 'column', gap: '16px',
    }}>
      <span className="section-title" style={{ fontSize: '11px' }}>{title}</span>
      {children}
    </div>
  )
}

// ── Profile defaults ───────────────────────────────────────────────────────
function defaultPrefs() {
  return {
    target_titles: [],
    target_locations: [],
    remote_ok: true,
    hybrid_ok: true,
    onsite_ok: false,
    min_salary: null,
    max_experience_years: 3,
    blocked_companies: [],
    required_keywords: [],
    negative_keywords: [],
    skill_sets: { must_have: [], strong: [], nice: [] },
    greenhouse_companies: [],
  }
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function Profile() {
  const [prefs, setPrefs] = useState(defaultPrefs())
  const [resume, setResume] = useState('')
  const [style, setStyle] = useState('')
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState('idle') // idle | saving | saved
  const [error, setError] = useState(null)

  useEffect(() => {
    getProfile()
      .then(data => {
        const p = { ...defaultPrefs(), ...data.preferences }
        p.skill_sets = { must_have: [], strong: [], nice: [], ...(data.preferences?.skill_sets ?? {}) }
        setPrefs(p)
        setResume(data.resume ?? '')
        setStyle(data.cover_letter_style ?? '')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function setSkill(tier, val) {
    setPrefs(p => ({ ...p, skill_sets: { ...p.skill_sets, [tier]: val } }))
  }

  function setPref(key, val) {
    setPrefs(p => ({ ...p, [key]: val }))
  }

  async function handleSave() {
    setSaveState('saving')
    setError(null)
    try {
      await saveProfile({ preferences: prefs, resume, cover_letter_style: style })
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2500)
    } catch (e) {
      setError(e.message)
      setSaveState('idle')
    }
  }

  const isComplete = prefs.target_titles.length > 0
    && prefs.skill_sets.must_have.length > 0
    && resume.trim().length > 0

  if (loading) {
    return (
      <div style={{ padding: '48px 24px', fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
        loading...
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '860px', margin: '0 auto', padding: '32px 24px' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '28px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '22px', fontWeight: 700, letterSpacing: '0.04em' }}>
            Profile
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
            Drives job scoring, scraper targeting, and AI cover letter drafting.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '11px',
            color: isComplete ? 'var(--score-high)' : 'var(--score-mid)',
          }}>
            {isComplete ? '● complete' : '● incomplete'}
          </span>
          <button
            className="btn btn-accent"
            onClick={handleSave}
            disabled={saveState === 'saving'}
          >
            {saveState === 'saving' ? 'Saving...' : saveState === 'saved' ? '✓ Saved' : 'Save Profile'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          marginBottom: '16px', padding: '10px 14px',
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#ef4444',
        }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

        {/* Targeting */}
        <Section title="Targeting">
          <TagList label="Target job titles" values={prefs.target_titles} onChange={v => setPref('target_titles', v)} />
          <TagList label="Target locations" values={prefs.target_locations} onChange={v => setPref('target_locations', v)} />
        </Section>

        {/* Work mode */}
        <Section title="Work Mode">
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            <Toggle label="Remote OK" checked={prefs.remote_ok} onChange={v => setPref('remote_ok', v)} />
            <Toggle label="Hybrid OK" checked={prefs.hybrid_ok} onChange={v => setPref('hybrid_ok', v)} />
            <Toggle label="Onsite OK" checked={prefs.onsite_ok} onChange={v => setPref('onsite_ok', v)} />
          </div>
        </Section>

        {/* Experience */}
        <Section title="Experience">
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            <NumberField
              label="Max experience required (years)"
              value={prefs.max_experience_years}
              onChange={v => setPref('max_experience_years', v)}
              placeholder="3"
            />
            <NumberField
              label="Min salary (optional)"
              value={prefs.min_salary}
              onChange={v => setPref('min_salary', v)}
              placeholder="e.g. 80000"
              nullable
            />
          </div>
        </Section>

        {/* Skills */}
        <Section title="Skills">
          <TagList label="Must-have — heavily penalize if missing" values={prefs.skill_sets.must_have} onChange={v => setSkill('must_have', v)} />
          <TagList label="Strong — significant score boost" values={prefs.skill_sets.strong} onChange={v => setSkill('strong', v)} />
          <TagList label="Nice-to-have — small boost" values={prefs.skill_sets.nice} onChange={v => setSkill('nice', v)} />
        </Section>

        {/* Filters */}
        <Section title="Filters">
          <TagList label="Blocked companies" values={prefs.blocked_companies} onChange={v => setPref('blocked_companies', v)} />
          <TagList label="Required keywords" values={prefs.required_keywords} onChange={v => setPref('required_keywords', v)} />
          <TagList label="Negative keywords — filter out matching jobs" values={prefs.negative_keywords} onChange={v => setPref('negative_keywords', v)} />
        </Section>

        {/* Greenhouse */}
        <Section title="Greenhouse Companies">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
            Board slugs to scrape via Greenhouse (e.g. <span style={{ color: 'var(--accent)' }}>stripe</span>, <span style={{ color: 'var(--accent)' }}>linear</span>).
          </div>
          <TagList values={prefs.greenhouse_companies} onChange={v => setPref('greenhouse_companies', v)} />
        </Section>

        {/* Resume */}
        <Section title="Resume">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)' }}>
            Markdown. Used by the AI cover letter drafter as context.
          </div>
          <textarea
            value={resume}
            onChange={e => setResume(e.target.value)}
            placeholder="Paste your resume in markdown format..."
            style={{
              width: '100%', minHeight: '320px', padding: '14px',
              background: 'var(--bg-elevated)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', color: 'var(--text)',
              fontFamily: 'var(--font-mono)', fontSize: '12px', lineHeight: 1.7,
              outline: 'none', resize: 'vertical',
            }}
            onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
          />
        </Section>

        {/* Cover letter style */}
        <Section title="Cover Letter Style Guide">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)' }}>
            Instructions for the AI drafter — tone, length, what to emphasize.
          </div>
          <textarea
            value={style}
            onChange={e => setStyle(e.target.value)}
            placeholder="e.g. Keep it under 250 words. Lead with impact. Avoid buzzwords..."
            style={{
              width: '100%', minHeight: '180px', padding: '14px',
              background: 'var(--bg-elevated)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', color: 'var(--text)',
              fontFamily: 'var(--font-body)', fontSize: '13px', lineHeight: 1.7,
              outline: 'none', resize: 'vertical',
            }}
            onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
          />
        </Section>

        {/* Bottom save */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '4px' }}>
          <button
            className="btn btn-accent"
            onClick={handleSave}
            disabled={saveState === 'saving'}
          >
            {saveState === 'saving' ? 'Saving...' : saveState === 'saved' ? '✓ Saved' : 'Save Profile'}
          </button>
        </div>

      </div>
    </div>
  )
}
