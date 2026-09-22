import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import type { BranchSummary, Story } from '../../types'
import { TextEditWindow } from '../textEdits/TextEditWindow'
import type { EditInitial } from '../textEdits/types'
import { RecipePending } from './RecipePending'
import { RecipeRunView } from './RecipeRunView'
import { RecipeSetup } from './RecipeSetup'
import type { RecipeSelection } from './recipeRunTypes'
import { useRecipeOperation } from './useRecipeOperation'
import './recipeRuns.css'

interface Props { initial?: RecipeSelection; runId?: string; branchId?: string; onClose: () => void; onBranch: (id: string) => void; focusOnClose?: () => HTMLElement | null }

export function RecipeDialog({ initial, runId, branchId, onClose, onBranch, focusOnClose }: Props) {
  const [edit, setEdit] = useState<EditInitial | null>(null)
  if (edit) return <TextEditWindow initial={edit} onClose={() => setEdit(null)} onBranch={onBranch} focusOnClose={() => document.querySelector<HTMLElement>('[data-recipe-proposal]')} />
  return <Modal open wide title="Run a writing recipe" description="Choose a workflow for exact text, inspect each request, and keep every result reviewable." onClose={onClose} focusOnClose={focusOnClose}><div className="dialog-body recipe-workspace form-stack">
    {runId ? <RecipeRunView id={runId} onEdit={setEdit} /> : initial && <RecipeContext initial={initial} branchId={branchId} onEdit={setEdit} />}
  </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Close recipe workspace</button></footer></Modal>
}

function RecipeContext({ initial, branchId = '', onEdit }: { initial: RecipeSelection; branchId?: string; onEdit: (value: EditInitial) => void }) {
  const [selected, setSelected] = useState(branchId)
  const fixed = 'branch_id' in initial.target.ref ? initial.target.ref.branch_id : ''
  const story = useQuery({ queryKey: ['story', initial.target.ref.story_id], queryFn: () => api<Story>(`/stories/${initial.target.ref.story_id}`) })
  return <><ErrorNotice message={story.error?.message} />{story.isPending && <Loading label="Opening this Story's recipe context…" />}{story.data && <RecipeContextChoice initial={initial} story={story.data} selected={fixed || selected} fixed={!!fixed} onSelect={setSelected} onEdit={onEdit} />}</>
}

function RecipeContextChoice({ initial, story, selected, fixed, onSelect, onEdit }: { initial: RecipeSelection; story: Story; selected: string; fixed: boolean; onSelect: (id: string) => void; onEdit: (value: EditInitial) => void }) {
  const contextId = selected || (story.branches.length === 1 ? story.branches[0].id : '')
  const branch = story.branches.find(item => item.id === contextId)
  return <>{!fixed && <label className="field"><span>Story telling used as context</span><select aria-label="Recipe context telling" value={contextId} onChange={event => onSelect(event.target.value)}><option value="">Choose a telling</option>{story.branches.map(item => <option key={item.id} value={item.id}>{item.name}{item.curation?.archived ? ' · archived' : ''}</option>)}</select><small>The selected text stays the destination. Only this telling supplies Story context.</small></label>}{branch && <RecipeCreation key={`${branch.id}:${initial.target.version}`} initial={initial} branch={branch} onEdit={onEdit} />}</>
}

function RecipeCreation({ initial, branch, onEdit }: { initial: RecipeSelection; branch: BranchSummary; onEdit: (value: EditInitial) => void }) {
  const operation = useRecipeOperation(`prospero:recipe-create:${branch.id}:${initial.target.version}`)
  if (operation.receipt.data) return <><RecipeRunView id={operation.receipt.data.id} onEdit={onEdit} /><button className="text-button" onClick={operation.clear}>Prepare another run for this selection</button></>
  if (operation.pending) return <RecipePending operation={operation} />
  return <><RecipeSetup initial={initial} branch={branch} busy={operation.busy} onSave={(body, preview) => void operation.send(`/branches/${branch.id}/recipe-runs`, { ...body, preview_hash: preview.preview_hash })} /><ErrorNotice message={operation.error} /></>
}
