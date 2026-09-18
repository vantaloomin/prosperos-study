import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen } from 'lucide-react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Story } from '../../types'
import { BookEditor } from './BookEditor'
import { BookReader, BookSearch } from './BookReader'
import type { BookDocument, Manuscript, Publication, ReadingTarget } from './types'
import '../../styles/manuscript.css'

export function ManuscriptWorkspace(props: { story: Story; branchId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['manuscript', props.story.id], queryFn: () => api<Manuscript>(`/stories/${props.story.id}/manuscript`) })
  return <main className="manuscript-workspace"><header className="book-heading"><button className="button quiet" onClick={props.onClose}><ArrowLeft size={16} />Back to writing</button><div><span className="eyebrow">BOOK WORKSPACE</span><h1>{props.story.title}</h1></div><BookOpen aria-hidden="true" /></header>
    <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Opening the manuscript…" />}{query.data && <WorkspaceContent {...props} manuscript={query.data} />}
  </main>
}

function WorkspaceContent({ story, branchId, manuscript }: { story: Story; branchId: string; manuscript: Manuscript }) {
  const [tab, setTab] = useState('organize'), [dirty, setDirty] = useState(false), [target, setTarget] = useState<ReadingTarget | null>(null)
  const action = useAction()
  const preview = useQuery({ queryKey: ['book-preview', story.id, manuscript.revision], enabled: tab !== 'organize', queryFn: () => api<Publication>(`/stories/${story.id}/manuscript/preview`) })
  const read = (value: ReadingTarget) => { setTarget(value); setTab('read') }
  const bookmark = (sceneId: string, nodeId: string, label: string) => action.run(async () => {
    const current = manuscript.document.bookmarks
    const found = current.some(mark => mark.scene_id === sceneId && mark.node_id === nodeId)
    const bookmarks = found ? current.filter(mark => mark.scene_id !== sceneId || mark.node_id !== nodeId) : [...current, { id: crypto.randomUUID(), scene_id: sceneId, node_id: nodeId, label: label.slice(0, 200) }]
    await api(`/stories/${story.id}/manuscript`, { expected_revision: manuscript.revision, document: { ...manuscript.document, bookmarks } }, 'PUT')
  })
  return <div className="book-content"><nav className="tabs book-tabs" aria-label="Manuscript views">{[['organize', 'Organize'], ['read', 'Read & bookmark'], ['search', 'Search'], ['publish', 'Publish']].map(([key, label]) => <button key={key} aria-pressed={tab === key} disabled={dirty && key !== 'organize'} onClick={() => setTab(key)}>{label}</button>)}</nav><ErrorNotice message={action.error || preview.error?.message} />
    {tab === 'organize' ? <SavedEditor key={manuscript.revision} manuscript={manuscript} story={story} branchId={branchId} onDirty={setDirty} /> : <>
      {preview.isPending && <Loading label="Assembling chosen tellings…" />}
      {preview.data && <><p className="book-stats">{preview.data.words.toLocaleString()} words · {preview.data.chapters.length} chapters · Saved version {manuscript.revision}</p>
        {tab === 'read' && <><details className="book-bookmarks"><summary>Bookmarks ({manuscript.document.bookmarks.length})</summary>{manuscript.document.bookmarks.map(mark => <button className="text-button" key={mark.id} onClick={() => read({ sceneId: mark.scene_id, nodeId: mark.node_id })}>{mark.label}</button>)}</details><BookReader book={preview.data} bookmarks={manuscript.document.bookmarks} target={target} onRead={setTarget} onBookmark={bookmark} busy={action.busy} /></>}
        {tab === 'search' && <BookSearch storyId={story.id} revision={manuscript.revision} onRead={read} />}
        {tab === 'publish' && <PublicationExport key={manuscript.revision} storyId={story.id} book={preview.data} />}
      </>}
    </>}
  </div>
}

function SavedEditor({ manuscript, story, branchId, onDirty }: { manuscript: Manuscript; story: Story; branchId: string; onDirty: (dirty: boolean) => void }) {
  const key = `roleplay:manuscript:${story.id}:${manuscript.revision}`
  const [draft, setDraft] = usePersistent<BookDocument>(key, manuscript.document)
  const cache = useQueryClient(), action = useAction()
  const changed = JSON.stringify(draft) !== JSON.stringify(manuscript.document)
  useEffect(() => { onDirty(changed) }, [changed, onDirty])
  const change = (next: BookDocument) => { setDraft(next); onDirty(JSON.stringify(next) !== JSON.stringify(manuscript.document)) }
  const save = () => action.run(async () => {
    const result = await api<Manuscript>(`/stories/${story.id}/manuscript`, { expected_revision: manuscript.revision, document: draft }, 'PUT')
    localStorage.removeItem(key); onDirty(false); cache.setQueryData(['manuscript', story.id], result)
  })
  return <><BookEditor value={draft} onChange={change} story={story} branchId={branchId} /><footer className="book-save"><span className="subtle">{changed ? 'Unsaved organization · draft kept on this device' : 'All organization saved'}</span><button className="button quiet" disabled={!changed || action.busy} onClick={() => change(manuscript.document)}>Discard organization changes</button><button className="button primary" disabled={action.busy || !draft.title.trim() || !changed} onClick={save}>Save manuscript</button></footer><ErrorNotice message={action.error} /></>
}

function PublicationExport({ storyId, book }: { storyId: string; book: Publication }) {
  const action = useAction()
  const [prepared, setPrepared] = useState<{ docx_url: string; epub_url: string; revision: number; words: number } | null>(null)
  const prepare = () => action.run(async () => setPrepared(await api(`/stories/${storyId}/manuscript/exports`, { expected_revision: book.revision })))
  return <section className="book-publication"><h2>Ready for the next reader</h2><p>Export the saved manuscript in chapter and scene order. DOCX includes editable headings and page numbers. EPUB includes a linked table of contents.</p><p className="subtle">The files contain the selected prose and publication details. Author’s notes, bookmarks, private context and model records stay in the workspace.</p><ol>{book.chapters.map(chapter => <li key={chapter.id}>{chapter.title} <small>· {chapter.scenes.length} scenes</small></li>)}</ol><button className="button primary" disabled={action.busy || !book.words} onClick={prepare}>{action.busy ? 'Preparing…' : 'Prepare publication files'}</button><ErrorNotice message={action.error} />{prepared && <div className="book-downloads" role="status"><p>Prepared version {prepared.revision} · {prepared.words.toLocaleString()} words</p><a className="button" href={prepared.docx_url} download>Download DOCX</a><a className="button" href={prepared.epub_url} download>Download EPUB</a></div>}</section>
}
