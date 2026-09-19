const labels: Record<string, string> = {
  recall_seconds: 'Prewriting recall',
  preparation_seconds: 'Context preparation', request_to_first_text_seconds: 'Request received to first text',
  writer_seconds: 'Writer attempt (including queue)', draft_ready_seconds: 'Attempt to usable draft',
  queue_seconds: 'Provider queue', first_text_seconds: 'Provider start to first text', inference_seconds: 'Provider request',
}

export function TimingDetails({ usage }: { usage: Record<string, unknown> }) {
  const values = { ...record(usage.timings), ...record(usage.scheduling) }
  const rows = Object.entries(values).filter(([key, value]) => labels[key] && typeof value === 'number' && Number.isFinite(value))
  if (!rows.length) return null
  return <details><summary>Observed timings</summary><dl>{rows.map(([key, value]) => <div key={key}><dt>{labels[key]}</dt><dd>{(value as number).toFixed(3)}s</dd></div>)}</dl><p className="subtle">Measured by this app. Draft readiness excludes cleanup while reading. Context preparation refers to the saved request; retrying reuses those inputs.</p></details>
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
