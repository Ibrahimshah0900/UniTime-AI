export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? 'brand--compact' : ''}`} aria-label="UniTime-AI">
      <div className="brand__mark" aria-hidden="true">U</div>
      {!compact && <div><strong>UniTime-AI</strong><span>Smart timetable, better campus</span></div>}
    </div>
  )
}
