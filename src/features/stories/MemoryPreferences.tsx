interface Settings { mode?: 'full' | 'long'; open_threads?: boolean; recall_limit?: number; canon_limit?: number; summary_recall?: boolean; summary_context?: boolean; writer_recall?: boolean; semantic_recall?: boolean; relationship_recall?: boolean; relationship_automatic?: boolean }
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
      <p className="subtle">Standard recall runs locally. Author notes, required Canon, and the latest passage still need to fit. Context budget shows the initial writer inputs. Scene and privileged review previews show their own coverage; exact drafts stay intact. Existing scene plans keep the memory settings they started with.</p>
      <label className="check-row"><input type="checkbox" checked={memory.open_threads ?? true} onChange={(event) => patch({ open_threads: event.target.checked })} /><span>Recall open threads<small className="subtle">Use accepted unresolved promises and questions to find earlier passages. This never resolves them automatically.</small></span></label>
      <SummaryPreferences memory={memory} patch={patch} />
      <label className="check-row"><input type="checkbox" checked={memory.writer_recall ?? false} onChange={event => patch({ writer_recall: event.target.checked })} /><span>Check earlier evidence before writing<small className="subtle">Adds one preparation request per comparison candidate using its writer model, then searches accepted prose on this path. Up to two searches and eight passages share the existing context allowance. Preparation can take up to 60 seconds; failed preparation keeps the original context. Final inputs and search decisions are saved with each draft. Character-lens writing and scene workflows do not use this option yet.</small></span></label>
      <SemanticPreferences memory={memory} patch={patch} />
      <RelationshipPreferences memory={memory} patch={patch} />
      <details className="advanced-settings"><summary>Recall allowance</summary><label className="field"><span>Maximum earlier excerpts</span><input type="number" min={1} max={16} value={memory.recall_limit ?? 8} onChange={(event) => patch({ recall_limit: Math.max(1, Math.min(16, Number(event.target.value) || 1)) })} /><small>The available context budget can reduce this number. Weak matches are left out.</small></label><label className="field"><span>Maximum Canon excerpts</span><input type="number" min={1} max={16} value={memory.canon_limit ?? 8} onChange={(event) => patch({ canon_limit: Math.max(1, Math.min(16, Number(event.target.value) || 1)) })} /><small>Writing, scene and privileged review steps use this allowance for collections set to relevant recall. Required entries keep their native rules.</small></label></details>
    </div>}
  </section>
}

function SemanticPreferences({ memory, patch }: { memory: Settings; patch: (value: Partial<Settings>) => void }) {
  if (!memory.writer_recall) return null
  return <label className="check-row"><input type="checkbox" checked={memory.semantic_recall ?? false} onChange={event => patch({ semantic_recall: event.target.checked })} /><span>Also search by meaning<small className="subtle">Requires an embedding model in each writer profile’s Semantic story recall settings. Searches permitted prose independently of keywords, then combines the rankings. Adds up to five embedding requests and 30 seconds per candidate, preparing at most 64 new passages each time. Keyword search continues while the cache warms or if embeddings fail. Up to 4,096 source chunks are supported.</small></span></label>
}

function RelationshipPreferences({ memory, patch }: { memory: Settings; patch: (value: Partial<Settings>) => void }) {
  return <div className="form-stack"><label className="check-row"><input type="checkbox" checked={memory.relationship_recall ?? false} onChange={event => patch({ relationship_recall: event.target.checked })} /><span>Use tentative relationship links<small className="subtle">Prepared links help prewriting recall find related original passages. They keep supporting quotes and distinguish events, intentions, testimony and knowledge claims. They never change accepted facts or plans. Prepare existing passages in Writing tools → Story memory → Relationship links. Enable Check earlier evidence before writing to use them in new drafts.</small></span></label>
    {memory.relationship_recall && <label className="check-row"><input type="checkbox" checked={memory.relationship_automatic ?? false} onChange={event => patch({ relationship_automatic: event.target.checked })} /><span>Prepare links after accepted prose<small className="subtle">Uses the Primary Writer configuration for up to four new source passages per grouped update. Each request is limited to 60 seconds and 1,200 output tokens. Automatic work requires verified background interruption on that connection and yields to writing. Other connections support explicit preparation. Stopped or failed requests need an explicit retry.</small></span></label>}
  </div>
}

function SummaryPreferences({ memory, patch }: { memory: Settings; patch: (value: Partial<Settings>) => void }) {
  return <>
<label className="check-row"><input type="checkbox" checked={memory.summary_recall ?? false} onChange={event => patch({ summary_recall: event.target.checked })} /><span>Use reviewed summaries for story recall<small className="subtle">Reviewed summaries, topics and aliases help locate exact earlier prose. Prepare and review them in Writing tools → Story memory. Recall is local; generating summaries is a separate model request.</small></span></label>
<label className="check-row"><input type="checkbox" checked={memory.summary_context ?? false} onChange={event => patch({ summary_context: event.target.checked })} /><span>Allow reviewed summaries in context<small className="subtle">When space is tight, a shorter reviewed summary can replace an older excerpt. Summaries can omit detail or misinterpret it; exact grounding quotes and source links stay attached. Recent prose and required evidence stay exact. This makes no extra model calls.</small></span></label>
  </>
}
