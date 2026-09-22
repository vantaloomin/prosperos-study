import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { ModelProfile } from '../models/types'
import type { Routing } from '../workflow/types'
import { useEffect } from 'react'
import { useTextDocument } from '../textEdits/useTextDocument'
import { DocumentTools } from '../textEdits/DocumentTools'
import { retainLegacy } from '../textEdits/draftStorage'
import { SceneWorkspace } from './SceneWorkspace'
import '../../styles/scenes.css'

export function ScenePlans({ branch, profiles, routing, onBranch }: { branch: Branch; profiles: ModelProfile[]; routing: Routing; onBranch: (id: string) => void }) {
  const history = useQuery({ queryKey: ['scenes', branch.id], queryFn: () => api<{ id: string; title: string; created_at: string }[]>(`/branches/${branch.id}/scenes`) })
  const [selected, setSelected] = usePersistent(`roleplay:scene-selection:${branch.id}`, '')
  return <div className="form-stack">{!selected && <div><h3>Shape the next scene</h3><p className="subtle">Explore options and refine the beats before approving a plan. After drafting, two readers can check the prose, continuity and beat coverage. Your Story stays at its current point until you accept the scene.</p></div>}
    <label className="field"><span>Scene plans on this branch</span><select value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Start a new plan</option>{history.data?.map((run) => <option key={run.id} value={run.id}>{run.title} · {new Date(run.created_at).toLocaleString()}</option>)}</select></label>
    <ErrorNotice message={history.error?.message} />
    {selected ? <SceneWorkspace key={selected} id={selected} profiles={profiles} branch={branch} routing={routing} onBranch={onBranch} /> : <NewPlan key={branch.head_id} branch={branch} onCreated={setSelected} />}
  </div>
}

function NewPlan({ branch, onCreated }: { branch: Branch; onCreated: (id: string) => void }) {
  const key = `roleplay:scene-draft:${branch.id}:${branch.head_id}`
  const [draft, storeDraft] = usePersistent(key, { title: '', direction: '', propose_options: true, dialogue_split: false })
  const setDraft = (next: typeof draft) => storeDraft({ ...next, direction: '' })
  const goal = useTextDocument({ kind: 'document', story_id: branch.story_id, branch_id: branch.id, purpose: 'scene-goal' })
  useEffect(() => {
    try {
      const legacy = JSON.parse(localStorage.getItem(key) ?? 'null') as typeof draft | null
      if (legacy?.direction) retainLegacy({ kind: 'document', story_id: branch.story_id, branch_id: branch.id, purpose: 'scene-goal' }, key, legacy.direction, () => localStorage.setItem(key, JSON.stringify({ ...legacy, direction: '' })))
    } catch { /* Keep the old draft if it cannot be copied safely. */ }
  }, [key, branch.story_id, branch.id])
  const action = useAction()
  const create = () => action.run(async () => {
    const source = await goal.controller.flush()
    if (source.text !== goal.text) throw new Error('The scene goal changed. Review its current text before saving a plan.')
    const result = await api<{ id: string }>(`/branches/${branch.id}/scenes`, { ...draft, direction: source.text, expected_document_version: source.version, expected_revision: branch.revision, operation_id: operationId() })
    onCreated(result.id)
  })
  return <div className="form-stack"><label className="field"><span>Plan title</span><input maxLength={120} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="A conversation at the station" /></label>
    <label className="field"><span>Scene goal</span><textarea aria-label="Scene goal" rows={5} maxLength={30000} value={goal.text} disabled={action.busy || goal.phase === 'loading'} onChange={(event) => goal.controller.edit(event.target.value)} placeholder="A goal for this planned scene only. What should it explore, and what stays the player’s choice?" /></label>
    <p className="subtle">This unsent goal belongs to {branch.name}. Saving a plan freezes its own copy at the current Story point and clears this draft.</p><DocumentTools draft={goal} disabled={action.busy} />
    <label className="check-row"><input type="checkbox" checked={draft.propose_options} onChange={(event) => setDraft({ ...draft, propose_options: event.target.checked })} />Explore four options before expanding the beats</label>
    <label className="check-row"><input type="checkbox" checked={draft.dialogue_split ?? false} onChange={(event) => setDraft({ ...draft, dialogue_split: event.target.checked })} />Give spoken lines to a separate dialogue writer</label><p className="subtle">Use this for scenes with conversation. The drafter leaves dialogue slots; the dialogue writer fills them while preserving narration.</p>
    <p className="subtle">Save the starting point first. You’ll preview each model request before sending it. Models and prompts are available in Models by step.</p><ErrorNotice message={action.error} />
    <button className="button primary" disabled={action.busy || goal.phase !== 'ready' || !draft.title.trim() || !goal.text.trim()} onClick={create}>Save scene goal</button>
  </div>
}
