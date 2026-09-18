import { useState } from 'react'
import { ArrowDown, ArrowUp, Plus } from 'lucide-react'
import { Field } from '../../components/Fields'
import type { Story } from '../../types'
import { ScenePicker } from './ScenePicker'
import { moveItem, removeScene, type BookDocument, type SceneSelection } from './types'

export function BookEditor({ value, onChange, story, branchId }: { value: BookDocument; onChange: (value: BookDocument) => void; story: Story; branchId: string }) {
  const [picking, setPicking] = useState<{ chapterId: string; scene?: SceneSelection } | null>(null)
  const patch = (next: Partial<BookDocument>) => onChange({ ...value, ...next })
  const chapter = (id: string, next: Partial<BookDocument['chapters'][number]>) => patch({ chapters: value.chapters.map(item => item.id === id ? { ...item, ...next } : item) })
  const select = (scene: SceneSelection, nodeIds: string[]) => {
    const target = value.chapters.find(item => item.id === picking?.chapterId)!
    const scenes = picking?.scene ? target.scenes.map(item => item.id === scene.id ? scene : item) : [...target.scenes, scene]
    patch({ chapters: value.chapters.map(item => item.id === target.id ? { ...item, scenes } : item), bookmarks: value.bookmarks.filter(mark => mark.scene_id !== scene.id || nodeIds.includes(mark.node_id)) })
    setPicking(null)
  }
  const transfer = (scene: SceneSelection, target: string) => patch({ chapters: value.chapters.map(item => ({ ...item, scenes: item.id === target ? [...item.scenes, scene] : item.scenes.filter(other => other.id !== scene.id) })) })
  return <div className="form-stack book-editor"><div className="book-metadata"><Field label="Book title" value={value.title} maxLength={200} onChange={event => patch({ title: event.target.value })} /><Field label="Author" value={value.author} maxLength={200} onChange={event => patch({ author: event.target.value })} /><Field label="Publication language" value={value.language} maxLength={40} onChange={event => patch({ language: event.target.value })} hint="Language tag, such as en or fr-CA." /></div>
    <div className="book-options"><label className="check-row"><input type="checkbox" checked={value.include_contributions} onChange={event => patch({ include_contributions: event.target.checked })} />Include character contributions</label><label className="check-row"><input type="checkbox" checked={value.scene_headings} onChange={event => patch({ scene_headings: event.target.checked })} />Print scene titles</label></div>
    <p className="subtle">Arrange chapters and choose a telling for each scene. Reordering here changes the book’s reading order; story history stays intact.</p>
    {!value.chapters.length && <div className="book-empty"><h2>Give the story a shape</h2><p>Add a chapter, then select the scenes that belong in it.</p></div>}
    {value.chapters.map((item, index) => <section className="book-chapter" key={item.id} aria-label={`Chapter ${index + 1}`}><header><span className="eyebrow">CHAPTER {index + 1}</span><OrderButtons label={`chapter ${index + 1}`} index={index} count={value.chapters.length} move={direction => patch({ chapters: moveItem(value.chapters, index, direction) })} /><button className="text-button" disabled={!!item.scenes.length} title={item.scenes.length ? 'Move or remove scenes first' : 'Remove empty chapter'} onClick={() => patch({ chapters: value.chapters.filter(other => other.id !== item.id) })}>Remove chapter</button></header>
      <Field label={`Chapter ${index + 1} title`} value={item.title} maxLength={200} onChange={event => chapter(item.id, { title: event.target.value })} />
      <ol className="book-scenes">{item.scenes.map((scene, sceneIndex) => <li key={scene.id}><div className="book-scene-title"><strong>{scene.title}</strong><small>{story.branches.find(branch => branch.id === scene.branch_id)?.name ?? 'Saved telling'}</small></div><div className="book-scene-actions"><OrderButtons label={scene.title} index={sceneIndex} count={item.scenes.length} move={direction => chapter(item.id, { scenes: moveItem(item.scenes, sceneIndex, direction) })} /><button className="button quiet" onClick={() => setPicking({ chapterId: item.id, scene })}>Choose telling</button><label className="field"><span className="sr-only">Chapter for {scene.title}</span><select aria-label={`Chapter for ${scene.title}`} value={item.id} onChange={event => transfer(scene, event.target.value)}>{value.chapters.map(choice => <option key={choice.id} value={choice.id}>{choice.title}</option>)}</select></label><button className="text-button" onClick={() => onChange(removeScene(value, scene.id))}>Remove scene</button></div></li>)}</ol>
      <button className="button quiet" onClick={() => setPicking({ chapterId: item.id })}><Plus size={15} />Add scene to chapter {index + 1}</button>
    </section>)}
    <button className="button" onClick={() => patch({ chapters: [...value.chapters, { id: crypto.randomUUID(), title: `Chapter ${value.chapters.length + 1}`, scenes: [] }] })}><Plus size={16} />Add chapter</button>
    {picking && <ScenePicker story={story} branchId={branchId} scene={picking.scene} onChoose={select} onClose={() => setPicking(null)} />}
  </div>
}

function OrderButtons({ label, index, count, move }: { label: string; index: number; count: number; move: (direction: number) => void }) {
  return <span className="book-order"><button className="icon-button" aria-label={`Move ${label} earlier`} disabled={index === 0} onClick={() => move(-1)}><ArrowUp size={15} /></button><button className="icon-button" aria-label={`Move ${label} later`} disabled={index === count - 1} onClick={() => move(1)}><ArrowDown size={15} /></button></span>
}
