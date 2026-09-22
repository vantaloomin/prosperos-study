import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { WritingSelect } from './WritingSelect'
import { useWritingPins, useWritingResources } from './useWritingResources'
import type { WritingPins, WritingResource } from './types'

export function StoryWritingPreferences({ storyId, onSaved }: { storyId: string; onSaved: () => void }) {
  const pins = useWritingPins(storyId)
  const resources = useWritingResources()
  if (pins.error || resources.error) return <ErrorNotice message={pins.error?.message || resources.error?.message} />
  if (!pins.data || !resources.data) return <Loading label="Opening writing defaults…" />
  return <PreferencesForm storyId={storyId} initial={pins.data} resources={resources.data} onSaved={onSaved} />
}

function PreferencesForm({ storyId, initial, resources, onSaved }: { storyId: string; initial: WritingPins; resources: WritingResource[]; onSaved: () => void }) {
  const [choice, setChoice] = useState(initial)
  const operation = useRef({ id: operationId(), payload: '' })
  const action = useAction()
  const save = () => action.run(async () => {
    const payload = JSON.stringify(choice)
    if (operation.current.payload !== payload) operation.current = { id: operationId(), payload }
    await api(`/stories/${storyId}/writing-preferences`, { style: choice.style, recipe: choice.recipe, expected_revision: choice.story_revision, operation_id: operation.current.id }, 'PUT')
    onSaved()
  })
  return <div className="form-stack"><p className="subtle">Choose versions for future writing in this Story. Publishing a newer version in the Library keeps these choices pinned until you adopt it here.</p><WritingSelect label="Story writing style" kind="style" value={choice.style} resources={resources} onChange={style => setChoice({ ...choice, style })} /><WritingSelect label="Story writing recipe" kind="recipe" draftOnly value={choice.recipe} resources={resources} onChange={recipe => setChoice({ ...choice, recipe })} /><p className="subtle">A recipe's style takes precedence over this Story's style. Writing tools can override either for a single request. Review and revision recipes are selected with a passage.</p><ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy} onClick={save}>Save writing defaults</button></div>
}
