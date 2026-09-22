import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Field } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import { newWritingDraft, type Starter, type WritingDraft, type WritingKind, type WritingResource } from './types'
import './writing.css'
import { UnsupportedSettings } from './UnsupportedSettings'
import { PresetOrigins } from '../migration/PresetOrigins'

const WritingEditor = lazy(() => import('./WritingEditor').then(module => ({ default: module.WritingEditor })))
const WritingBundleExport = lazy(() => import('./WritingBundleExport').then(module => ({ default: module.WritingBundleExport })))
const WritingBundleImport = lazy(() => import('./WritingBundleImport').then(module => ({ default: module.WritingBundleImport })))
const SampleAnalysisHistory = lazy(() => import('./SampleAnalysis').then(module => ({ default: module.SampleAnalysisHistory })))
type EditorState = { draft: WritingDraft; resource?: WritingResource } | null
type BundleState = WritingResource | 'import' | null

export function WritingLibrary() {
  const query = useQuery({ queryKey: ['writing-resources'], queryFn: () => api<WritingResource[]>('/writing-resources?include_archived=true') })
  const starters = useQuery({ queryKey: ['writing-starters'], queryFn: () => api<Starter[]>('/writing-starters') })
  const [kind, setKind] = useState<WritingKind>('style')
  const [search, setSearch] = useState('')
  const [archived, setArchived] = useState(false)
  const [editor, setEditor] = useState<EditorState>(null)
  const [bundle, setBundle] = useState<BundleState>(null)
  const [analysisHistory, setAnalysisHistory] = useState(false)
  const action = useAction()
  const resources = query.data ?? []
  const visible = resources.filter(item => item.kind === kind && (archived || !item.archived) && `${item.name} ${item.description}`.toLowerCase().includes(search.toLowerCase()))
  const archive = (item: WritingResource) => action.run(async () => { await api(`/writing-resources/${item.asset_id}/archive`, { operation_id: operationId(), expected_revision: item.revision, archived: !item.archived }, 'PUT') })
  const duplicate = (item: WritingResource) => setEditor({ draft: { ...newWritingDraft(item.kind, item), name: `${item.name} copy`.slice(0, 120) } })
  return <section className="writing-library form-stack"><div className="section-heading"><div><h2>Your way with words</h2><p className="subtle">Save a voice you enjoy and return to the writing routines that work for you.</p></div><button className="button primary" onClick={() => setEditor({ draft: newWritingDraft(kind) })}>New {kind === 'style' ? 'style profile' : 'recipe'}</button></div>
    <div className="tabs" aria-label="Writing Library type"><button aria-pressed={kind === 'style'} onClick={() => setKind('style')}>Style profiles</button><button aria-pressed={kind === 'recipe'} onClick={() => setKind('recipe')}>Writing recipes</button></div>
    <button className="button" onClick={() => setAnalysisHistory(true)}>Saved sample analyses</button>
    <button className="button" onClick={() => setBundle('import')}>Import writing bundle</button><Field label="Find a writing resource" type="search" value={search} onChange={event => setSearch(event.target.value)} /><label className="check-row"><input type="checkbox" checked={archived} onChange={event => setArchived(event.target.checked)} />Include archived resources</label>
    <ErrorNotice message={query.error?.message || action.error} />{query.isPending && <Loading label="Opening writing tools…" />}
    <div className="writing-resource-grid">{visible.map(item => <article className="writing-resource-card form-stack" key={item.asset_id}><div><span className="eyebrow">{item.kind === 'style' ? 'Style profile' : 'Writing recipe'} · v{item.number}{item.archived ? ' · archived' : ''}</span><h3>{item.name}</h3><p>{item.description || (item.kind === 'style' ? 'Your prose preferences, saved for another story.' : 'A reusable set of writing instructions.')}</p></div><div className="writing-resource-actions"><button className="button" onClick={() => setEditor({ draft: newWritingDraft(item.kind, item), resource: item })}>Open & edit</button><button className="text-button" onClick={() => duplicate(item)}>Duplicate</button><button className="text-button" onClick={() => setBundle(item)}>Export</button><button className="text-button" disabled={action.busy} onClick={() => archive(item)}>{item.archived ? 'Unarchive' : 'Archive'}</button></div><UnsupportedSettings value={item.unsupported} /><VersionHistory item={item} onDuplicate={duplicate} onExport={setBundle} /></article>)}</div>
    <EmptyWriting pending={query.isPending} count={visible.length} search={search} kind={kind} />
    {kind === 'recipe' && <section className="form-stack"><h3>A few places to begin</h3><ErrorNotice message={starters.error?.message} /><div className="writing-resource-grid">{starters.data?.map(item => <article key={item.key} className="writing-resource-card form-stack"><h4>{item.name}</h4><p>{item.description}</p><button className="button" onClick={() => setEditor({ draft: newWritingDraft('recipe', item) })}>Customize {item.name}</button></article>)}</div></section>}
    <EditorView editor={editor} resources={resources} onClose={() => setEditor(null)} />
    <AnalysisHistoryView open={analysisHistory} onClose={() => setAnalysisHistory(false)} />
    <BundleView state={bundle} onClose={() => setBundle(null)} onImported={item => { setBundle(null); setKind(item.kind); setSearch(item.name) }} />
  </section>
}

function AnalysisHistoryView({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open && <Suspense fallback={<Loading />}><SampleAnalysisHistory onClose={onClose} /></Suspense>
}

function BundleView({ state, onClose, onImported }: { state: BundleState; onClose: () => void; onImported: (item: WritingResource) => void }) {
  if (!state) return null
  return <Suspense fallback={<Loading label="Opening portable writing tools…" />}>{state === 'import' ? <WritingBundleImport onClose={onClose} onImported={onImported} /> : <WritingBundleExport resource={state} onClose={onClose} />}</Suspense>
}

function EmptyWriting({ pending, count, search, kind }: { pending: boolean; count: number; search: string; kind: WritingKind }) {
  if (pending || count) return null
  return <p className="subtle">{search ? 'No matching resources.' : `Create your first ${kind === 'style' ? 'style profile' : 'recipe'}. Published versions remain available to the Stories that use them.`}</p>
}

function EditorView({ editor, resources, onClose }: { editor: EditorState; resources: WritingResource[]; onClose: () => void }) {
  if (!editor) return null
  return <Suspense fallback={<Loading label="Opening writing editor…" />}><WritingEditor key={editor.resource?.id ?? `${editor.draft.kind}:${editor.draft.name}`} initial={editor.draft} resource={editor.resource} resources={resources} onClose={onClose} /></Suspense>
}

function VersionHistory({ item, onDuplicate, onExport }: { item: WritingResource; onDuplicate: (version: WritingResource) => void; onExport: (version: WritingResource) => void }) {
  const [open, setOpen] = useState(false)
  const history = useQuery({ queryKey: ['writing-history', item.asset_id, item.id], queryFn: () => api<WritingResource[]>(`/writing-resources/${item.asset_id}/versions`), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Earlier versions</summary><ErrorNotice message={history.error?.message} />{history.isPending && open && <Loading label="Reading versions…" />}{open && history.data?.map(version => <div key={version.id}><div className="writing-version"><span>v{version.number} · {version.name}<small>{version.note}</small></span><div className="writing-resource-actions"><button className="text-button" onClick={() => onDuplicate(version)}>Copy this version</button><button className="text-button" onClick={() => onExport(version)}>Export v{version.number}</button></div></div>{version.kind === 'recipe' && <PresetOrigins versionId={version.id} />}</div>)}</details>
}
