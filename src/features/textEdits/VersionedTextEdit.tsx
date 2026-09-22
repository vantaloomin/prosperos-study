import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import type { StorySummary } from '../../types'
import { TextEditWindow } from './TextEditWindow'
import type { TextTarget } from './types'

export type VersionedSource = { kind: 'library-field' | 'writing-field'; asset_id: string } | { kind: 'prompt'; prompt_key: string; prompt_scope: 'story' | 'workspace' }
interface Catalog { name: string; version_id: string; number: number; options: { ref: TextTarget; label: string }[] }

export function VersionedTextEdit({ source, expectedEdition, storyId, onClose, focusOnClose }: { source: VersionedSource; expectedEdition: string; storyId?: string; onClose: () => void; focusOnClose?: () => HTMLElement | null }) {
  const [selectedStory, setStory] = useState(storyId ?? '')
  const [chosen, setChosen] = useState<TextTarget | null>(null)
  const stories = useQuery({ queryKey: ['stories'], queryFn: () => api<StorySummary[]>('/stories'), enabled: !storyId })
  const catalog = useQuery({ queryKey: ['text-target-catalog', source, selectedStory], queryFn: () => api<Catalog>('/text-targets/catalog', { ...source, story_id: selectedStory }), enabled: !!selectedStory })
  if (chosen) return <TextEditWindow initial={{ target: chosen, expectedEdition }} onClose={onClose} onBranch={() => {}} focusOnClose={focusOnClose} />
  return <Modal open title="Choose text to change" description="Choose one published text field. Review the wording before publishing a new edition." onClose={onClose} focusOnClose={focusOnClose}><div className="dialog-body form-stack">
    {!storyId && <label className="field"><span>Keep this edit history in</span><select aria-label="Edit history Story" value={selectedStory} onChange={event => setStory(event.target.value)}><option value="">Choose a Story</option>{stories.data?.map(story => <option key={story.id} value={story.id}>{story.title}</option>)}</select><small>The Story keeps the proposal and receipt. Publication scope is shown with the selected text.</small></label>}
    <ErrorNotice message={stories.error?.message} /><ErrorNotice message={catalog.error?.message} />
    {!!selectedStory && catalog.isPending && <Loading label="Reading the published fields…" />}
    {catalog.data && <CatalogFields catalog={catalog.data} expectedEdition={expectedEdition} onChoose={setChosen} />}
  </div></Modal>
}

function CatalogFields({ catalog, expectedEdition, onChoose }: { catalog: Catalog; expectedEdition: string; onChoose: (ref: TextTarget) => void }) {
  const [index, setIndex] = useState(0)
  const stale = catalog.version_id !== expectedEdition
  return <><p>{catalog.name} · v{catalog.number}</p>{stale && <ErrorNotice message="A newer edition is available. Close and reopen the editor before choosing its text." />}<label className="field"><span>Text field</span><select aria-label="Published text field" value={index} onChange={event => setIndex(Number(event.target.value))}>{catalog.options.map((option, position) => <option key={position} value={position}>{option.label}</option>)}</select></label><button className="button primary" disabled={stale || !catalog.options[index]} onClick={() => onChoose(catalog.options[index].ref)}>Review this field</button></>
}
