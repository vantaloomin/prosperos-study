import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Bookmark, Publication, ReadingTarget } from './types'

export function BookSearch({ storyId, revision, onRead }: { storyId: string; revision: number; onRead: (target: ReadingTarget) => void }) {
  const [input, setInput] = useState(''), [query, setQuery] = useState(''), [offset, setOffset] = useState(0)
  const result = useQuery({ queryKey: ['book-search', storyId, revision, query, offset], enabled: !!query,
    queryFn: () => api<{ matches: { chapter: string; scene: string; scene_id: string; node_id: string; excerpt: string }[]; total: number; has_more: boolean }>(`/stories/${storyId}/manuscript/search?q=${encodeURIComponent(query)}&offset=${offset}`) })
  return <section className="book-search"><form onSubmit={event => { event.preventDefault(); setQuery(input.trim()); setOffset(0) }}><Field label="Search the manuscript" value={input} maxLength={200} onChange={event => setInput(event.target.value)} placeholder="A name, a phrase, an unfinished thread…" /><button className="button" disabled={!input.trim()}>Search all chapters</button></form><ErrorNotice message={result.error?.message} />
    {query && result.isPending && <Loading label="Searching the book…" />}{result.data && <><p role="status" className="subtle">{result.data.total} matching passages in the saved manuscript.</p><ul className="book-search-results">{result.data.matches.map((match, index) => <li key={index}><button onClick={() => onRead({ sceneId: match.scene_id, nodeId: match.node_id })}><strong>{match.chapter} · {match.scene}</strong><span>{match.excerpt}</span></button></li>)}</ul><div className="button-row">{offset > 0 && <button className="button quiet" onClick={() => setOffset(offset - 50)}>Previous results</button>}{result.data.has_more && <button className="button quiet" onClick={() => setOffset(offset + 50)}>More results</button>}</div></>}
  </section>
}

export function BookReader({ book, bookmarks, target, onBookmark, onRead, busy }: { book: Publication; bookmarks: Bookmark[]; target: ReadingTarget | null; onBookmark: (sceneId: string, nodeId: string, label: string) => void; onRead: (target: ReadingTarget | null) => void; busy: boolean }) {
  const [chapterId, setChapterId] = useState(book.chapters[0]?.id ?? '')
  const chapter = book.chapters.find(item => target && item.scenes.some(scene => scene.id === target.sceneId)) ?? book.chapters.find(item => item.id === chapterId) ?? book.chapters[0]
  useEffect(() => {
    if (!target) return
    const element = document.getElementById(`book-${target.sceneId}-${target.nodeId ?? 'heading'}`)
    element?.scrollIntoView({ block: 'center' }); element?.focus({ preventScroll: true })
  }, [target])
  if (!chapter) return <p>Add a chapter and a scene to start reading.</p>
  return <div className="book-reading"><label className="field"><span>Read chapter</span><select aria-label="Read chapter" value={chapter.id} onChange={event => { setChapterId(event.target.value); onRead(null) }}>{book.chapters.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
    <article className="book-prose"><h2>{chapter.title}</h2>{chapter.scenes.map((scene, index) => <section key={scene.id}><header id={`book-${scene.id}-heading`} tabIndex={-1}><span className="eyebrow">SCENE {index + 1} · {scene.telling}</span><h3>{scene.title}</h3>{scene.changed && <p className="subtle">This telling has changed since selection. The book keeps the selected passages. Use “Choose telling” to update it.</p>}</header>{scene.passages.map(passage => <div className="book-passage" id={`book-${scene.id}-${passage.node_id}`} key={passage.node_id} tabIndex={-1}><p className="prose">{passage.text}</p><button className="text-button" disabled={busy} onClick={() => onBookmark(scene.id, passage.node_id, `${scene.title} · ${passage.text.slice(0, 50)}`)}>{bookmarks.some(mark => mark.scene_id === scene.id && mark.node_id === passage.node_id) ? 'Remove bookmark' : 'Bookmark passage'}</button></div>)}</section>)}</article>
  </div>
}
