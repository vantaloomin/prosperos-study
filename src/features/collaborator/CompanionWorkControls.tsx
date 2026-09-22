import { RevisionBoundary, TargetScope } from '../textEdits/EditPresentation'
import type { EditAction } from '../textEdits/types'
import { lazy, Suspense } from 'react'
import type { CompanionContext } from './contextTypes'
import { discussion, isTextTask, taskLabels, type CompanionTask, type CompanionWork } from './workTypes'

const inheritedWriting = { style: 'inherit', recipe: 'inherit', variables: {} }
const RequestWritingChoices = lazy(() => import('../writing/RequestWritingChoices').then(module => ({ default: module.RequestWritingChoices })))
export function CompanionWorkControls({ storyId, value = discussion, onChange, target, locked }: { storyId: string; value?: CompanionWork; onChange: (value: CompanionWork) => void; target?: CompanionContext | null; locked: boolean }) {
  const editing = isTextTask(value.task)
  const choose = (task: CompanionTask) => onChange({ task, action: value.action, authority: 'suggest', ...(isTextTask(task) ? { writing: value.writing ?? inheritedWriting } : {}) })
  return <details className="side-work-controls"><summary>Task: {taskLabels[value.task]}{editing ? ` · ${value.authority === 'apply' ? 'apply when ready' : 'suggestion'}` : ''}</summary><fieldset disabled={locked} className="form-stack"><label className="field"><span>Companion task</span><select aria-label="Companion task" value={value.task} onChange={event => choose(event.target.value as CompanionTask)}>{Object.entries(taskLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    {editing && <><label className="field"><span>Text action</span><select aria-label="Companion text action" value={value.action} onChange={event => onChange({ ...value, action: event.target.value as EditAction })}><option value="replace">Replace selected text</option><option value="insert-before">Insert before selection</option><option value="insert-after">Insert after selection</option><option value="add">Add at the end</option><option value="update">Update the whole field</option></select></label><label className="field"><span>When the wording is ready</span><select aria-label="Companion edit permission" value={value.authority} onChange={event => onChange({ ...value, authority: event.target.value as CompanionWork['authority'] })}><option value="suggest">Show a proposal for my review</option><option value="apply">Apply this requested change</option></select></label>
      <TargetPermission target={target} work={value} />
      <Suspense fallback={<p>Opening writing choices…</p>}><RequestWritingChoices storyId={storyId} value={value.writing ?? inheritedWriting} onChange={writing => onChange({ ...value, writing })} recipePurpose="revise" /></Suspense></>}
    {value.task === 'compare-tellings' && <p className="subtle">Pin a saved comparison to keep the two source revisions explicit.</p>}
  </fieldset></details>
}

function TargetPermission({ target, work }: { target?: CompanionContext | null; work: CompanionWork }) {
  if (target?.target.kind !== 'text') return <p className="subtle">Send or pin an exact text selection before requesting a text change.</p>
  const text = target.target.snapshot
  return <><p className="subtle">Destination: {text.label}. {work.authority === 'apply' ? 'Sending authorizes this one text change at its saved version. A changed target stays a proposal for review.' : 'The result stays a proposal until you apply it.'}</p>{work.authority === 'apply' && <><TargetScope target={text.ref} />{text.ref.kind === 'passage' && <RevisionBoundary />}</>}</>
}
