import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Field } from '../../components/Fields'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Story } from '../../types'
import type { SceneSelection } from './types'

interface Source { branch_id: string; head_id: string; revision: number; passages: { id: string; role: string; excerpt: string }[] }

function initialPassage(source: Source, selected: string | undefined, end = false) {
  if (selected && source.passages.some(item => item.id === selected)) return selected
  return (end ? source.passages.at(-1) : source.passages[0])?.id ?? ''
}

export function ScenePicker({ story, branchId, scene, onChoose, onClose }: { story: Story; branchId: string; scene?: SceneSelection; onChoose: (scene: SceneSelection, nodeIds: string[]) => void; onClose: () => void }) {
  const [branch, setBranch] = useState(scene?.branch_id ?? branchId)
  const query = useQuery({ queryKey: ['manuscript-sources', story.id, branch], queryFn: () => api<Source>(`/stories/${story.id}/manuscript/sources?branch_id=${branch}`) })
  return <Modal open onClose={onClose} title={scene ? 'Choose this scene’s telling' : 'Add a scene'} description="Select accepted passages from a telling. This selection stays fixed until you change it.">
    <div className="dialog-body form-stack"><label className="field"><span>Telling</span><select aria-label="Telling" value={branch} onChange={event => setBranch(event.target.value)}>{story.branches.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
      {query.data && <PassageChoice key={branch + ':' + query.data.head_id} source={query.data} scene={scene} onChoose={onChoose} />}
    </div>
  </Modal>
}

function PassageChoice({ source, scene, onChoose }: { source: Source; scene?: SceneSelection; onChoose: (scene: SceneSelection, nodeIds: string[]) => void }) {
  const [title, setTitle] = useState(scene?.title ?? 'Untitled scene')
  const [from, setFrom] = useState(initialPassage(source, scene?.from_node_id))
  const [through, setThrough] = useState(initialPassage(source, scene?.through_node_id, true))
  const start = source.passages.findIndex(item => item.id === from), end = source.passages.findIndex(item => item.id === through)
  const valid = title.trim() && start >= 0 && end >= start
  const options = source.passages.map((item, index) => <option key={item.id} value={item.id}>{index + 1}. {item.excerpt}</option>)
  return <><Field label="Scene title" value={title} maxLength={200} onChange={event => setTitle(event.target.value)} />
    <label className="field"><span>First passage</span><select aria-label="First passage" value={from} onChange={event => setFrom(event.target.value)}>{options}</select></label>
    <label className="field"><span>Last passage</span><select aria-label="Last passage" value={through} onChange={event => setThrough(event.target.value)}>{options}</select></label>
    {!source.passages.length ? <p>No accepted prose in this telling yet.</p> : <p className="subtle">{end >= start ? end - start + 1 : 0} passages selected. Author’s notes are excluded. Scene drafts must be accepted before they can appear here.</p>}
    <p className="subtle">Bookmarks outside the new selection will be removed when you save the manuscript.</p>
    <button className="button primary" disabled={!valid} onClick={() => onChoose({ id: scene?.id ?? crypto.randomUUID(), title: title.trim(), branch_id: source.branch_id, head_id: source.head_id, from_node_id: from, through_node_id: through }, source.passages.slice(start, end + 1).map(item => item.id))}>Use these passages</button>
  </>
}
