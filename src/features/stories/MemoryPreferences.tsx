interface Settings { mode?: 'full' | 'long'; open_threads?: boolean; recall_limit?: number; canon_limit?: number; summary_recall?: boolean; summary_context?: boolean }
interface Props { value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void }

export function MemoryPreferences({ value, onChange }: Props) {
  const memory = (value.memory ?? {}) as Settings
  const mode = memory.mode ?? 'full'
  const patch = (change: Partial<Settings>) => onChange({ ...value, memory: { ...memory, ...change } })
  return <section className="form-stack">
    <fieldset className="setup-choices"><legend className="field-label">Story memory</legend>
      <label className={'setup-choice ' + (mode === 'full' ? 'selected' : '')}>
        <input type="radio" name="story-memory" value="full" checked={mode === 'full'} onChange={() => patch({ mode: 'full' })} />
        <span><strong>Full history</strong><small>Send the complete selected path. Writing pauses if it exceeds the model’s context allowance.</small></span>
      </label>
      <label className={'setup-choice ' + (mode === 'long' ? 'selected' : '')}>
        <input type="radio" name="story-memory" value="long" checked={mode === 'long'} onChange={() => patch({ mode: 'long' })} />
        <span><strong>Long story</strong><small>Keep recent prose and recall relevant earlier passages. Every original stays in your story.</small></span>
      </label>
    </fieldset>
    {mode === 'long' && <div className="form-stack">
      <p className="subtle">Recall runs locally and makes no extra model calls. Author notes, required Canon, and the latest passage still need to fit. Context budget shows exactly what the writer will receive. Scene and privileged review previews show their own coverage; exact drafts stay intact. Existing scene plans keep the memory settings they started with.</p>
      <label className="check-row"><input type="checkbox" checked={memory.open_threads ?? true} onChange={(event) => patch({ open_threads: event.target.checked })} /><span>Recall open threads<small className="subtle">Use accepted unresolved promises and questions to find earlier passages. This never resolves them automatically.</small></span></label>
      <SummaryPreferences memory={memory} patch={patch} />
      <details className="advanced-settings"><summary>Recall allowance</summary><label className="field"><span>Maximum earlier excerpts</span><input type="number" min={1} max={16} value={memory.recall_limit ?? 8} onChange={(event) => patch({ recall_limit: Math.max(1, Math.min(16, Number(event.target.value) || 1)) })} /><small>The available context budget can reduce this number. Weak matches are left out.</small></label><label className="field"><span>Maximum Canon excerpts</span><input type="number" min={1} max={16} value={memory.canon_limit ?? 8} onChange={(event) => patch({ canon_limit: Math.max(1, Math.min(16, Number(event.target.value) || 1)) })} /><small>Writing, scene and privileged review steps use this allowance for collections set to relevant recall. Required entries keep their native rules.</small></label></details>
    </div>}
  </section>
}

function SummaryPreferences({ memory, patch }: { memory: Settings; patch: (value: Partial<Settings>) => void }) {
  return <>
<label className="check-row"><input type="checkbox" checked={memory.summary_recall ?? false} onChange={event => patch({ summary_recall: event.target.checked })} /><span>Use reviewed summaries for story recall<small className="subtle">Reviewed summaries, topics and aliases help locate exact earlier prose. Prepare and review them in Writing tools → Story memory. Recall is local; generating summaries is a separate model request.</small></span></label>
<label className="check-row"><input type="checkbox" checked={memory.summary_context ?? false} onChange={event => patch({ summary_context: event.target.checked })} /><span>Allow reviewed summaries in context<small className="subtle">When space is tight, a shorter reviewed summary can replace an older excerpt. Summaries can omit detail or misinterpret it; exact grounding quotes and source links stay attached. Recent prose and required evidence stay exact. This makes no extra model calls.</small></span></label>
  </>
}
