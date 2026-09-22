import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Archive, Download, Upload } from 'lucide-react'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Selection, Story } from '../../types'
import { ArchiveVerification, type WriterVerification } from './ArchiveVerification'
import '../../styles/archives.css'

interface ArchiveFile {
  id: string; kind: 'backup' | 'import'; filename: string; sha256: string; byte_count: number; created_at: string; download_url: string
  summary: { writer_verification?: WriterVerification | null; version?: number; title: string; scope: string; include_sidebar: boolean; counts: Record<string, number>; running_jobs: number; stories: { id: string; title: string; archived: boolean }[] }
}
interface RestoreResult { receipt_id: string; story_ids: string[]; selection: Selection | Record<string, never> }
interface Props { story?: Story; selection: Selection; onOpen: (selection: Selection) => void }
const sizeLabel = (bytes: number) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`

export function ArchiveImport({ onOpen }: { onOpen: (selection: Selection) => void }) {
  const [file, setFile] = useState<ArchiveFile | null>(null)
  return <div className="archives-panel form-stack"><ArchiveUpload onReady={setFile} />{file && <ArchivePreview key={file.id} file={file} onOpen={onOpen} />}</div>
}

export function Archives({ story, selection, onOpen }: Props) {
  const query = useQuery({ queryKey: ['archives'], queryFn: () => api<ArchiveFile[]>('/archives') })
  const [selected, setSelected] = useState<ArchiveFile | null>(null)
  const files = (query.data ?? []).filter((file) => !story || file.summary.stories.some((item) => item.id === story.id))
  return <section className="archives-panel form-stack"><div><h2>{story ? 'Keep every path' : 'Backups & recovery'}</h2><p className="subtle">A private archive keeps saved history, working text, old Library versions, styles, recipes, model settings, prompts, tables and recorded results. Credentials, appearance settings and unsaved browser-only recovery copies are excluded.</p></div>
    <ArchiveCreate story={story} selection={selection} onReady={setSelected} />
    {!story && <ArchiveUpload onReady={setSelected} />}
    <ErrorNotice message={query.error?.message} />
    {selected && <ArchivePreview key={selected.id} file={selected} onOpen={onOpen} />}
    <div className="archive-history"><h3>Saved copies</h3>{query.isPending && <Loading label="Finding saved copies…" />}{files.map((file) => <button className="archive-row" aria-pressed={selected?.id === file.id} key={file.id} onClick={() => setSelected(file)}><Archive size={18} /><span><strong>{file.summary.title}</strong><small>{file.kind === 'import' ? 'Staged import' : 'Local backup'} · {new Date(file.created_at).toLocaleString()} · {sizeLabel(file.byte_count)}</small></span><span>{file.summary.counts.stories} stories</span></button>)}{!query.isPending && !files.length && <p className="subtle">Your saved copies will appear here.</p>}</div>
  </section>
}

function ArchiveCreate({ story, selection, onReady }: { story?: Story; selection: Selection; onReady: (file: ArchiveFile) => void }) {
  const [sidebar, setSidebar] = useState(false)
  const action = useAction()
  const create = () => action.run(async () => {
    onReady(await api<ArchiveFile>('/archives', { scope: story ? 'story' : 'workspace', story_id: selection.storyId || null, branch_id: selection.branchId || null, include_sidebar: sidebar }))
  })
  return <div className="archive-create form-stack"><p>{story ? 'Archive this Story, its connected Library items, effective settings and configuration versions used by its saved history.' : 'Back up all Stories, including archived Stories, reusable Library material and the full configuration history.'} Shared Canon collections remain shared when several Stories are restored together.</p><label className="check-row"><input type="checkbox" checked={sidebar} onChange={(event) => setSidebar(event.target.checked)} />Include private sidebar conversations, unsent questions, and their saved source archives</label><ErrorNotice message={action.error} /><button className="button primary" aria-disabled={action.busy} onClick={create}><Archive size={16} />{action.busy ? 'Preparing your copy…' : 'Create private archive'}</button><small>Saved locally beside this workspace's database. Download a copy to keep it elsewhere.</small></div>
}

function ArchiveUpload({ onReady }: { onReady: (file: ArchiveFile) => void }) {
  const action = useAction()
  const upload = (file?: File) => action.run(async () => {
    if (!file) return
    if (file.size > 128 * 1024 * 1024) throw new Error('Choose a Prospero’s Study JSON archive smaller than 128 MiB.')
    onReady(await api<ArchiveFile>('/archives/imports', { content: await file.text() }))
  })
  return <div className="archive-upload form-stack"><div><h3>Bring a Story back</h3><p className="subtle">Choose a Prospero’s Study JSON archive (including earlier Roleplay archives). Validation and preview happen before any Story is created. Existing Stories and Library items stay intact.</p></div><label className="archive-file-label"><Upload size={16} /><span>Choose archive file</span><input type="file" accept=".json,application/json" aria-label="Choose archive file" aria-disabled={action.busy} onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = '' }} /></label>{action.busy && <Loading label="Validating this archive…" />}<ErrorNotice message={action.error} /></div>
}

function useArchiveSourceCheck(file: ArchiveFile) {
  const check = useQuery({ queryKey: ['archive-source-review', file.id, file.sha256], queryFn: () => api<ArchiveFile>(`/archives/${file.id}/review`), enabled: !file.summary.writer_verification, retry: false })
  const verification = file.summary.writer_verification ?? check.data?.summary.writer_verification
  return { verification, reviewing: !verification, error: check.error?.message }
}

function ArchivePreview({ file, onOpen }: { file: ArchiveFile; onOpen: (selection: Selection) => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const operation = useRef(operationId())
  const action = useAction()
  const [restored, setRestored] = useState<RestoreResult | null>(null)
  const { verification, reviewing, error } = useArchiveSourceCheck(file)
  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: 'start' }) }, [])
  const restore = () => action.run(async () => { if (reviewing) return; setRestored(await api<RestoreResult>(`/archives/${file.id}/restore`, { operation_id: operation.current, sha256: file.sha256 })) })
  return <section className="archive-preview form-stack"><h3 ref={heading} tabIndex={-1}>{file.kind === 'import' ? 'Review this import' : 'Your archive is ready'}</h3><p>{file.summary.title}</p><ArchiveCounts counts={file.summary.counts} /><p className="subtle">{sizeLabel(file.byte_count)} · Format version {file.summary.version ?? 1} · {file.summary.include_sidebar ? 'Includes private sidebar conversations and saved unsent questions' : 'Sidebar conversations and unsent questions excluded'}</p>
    <ul className="archive-story-list">{file.summary.stories.map((item) => <li key={item.id}>{item.title}{item.archived && ' · archived'}</li>)}</ul>
    <p className="subtle">Restore creates new copies of Stories and Library items, preserving their shared links. Prompts and tables are pinned for the restored Stories; your workspace defaults stay in place. Imported model profiles need their connection credentials configured again.</p>
    <p className="subtle">Saved prose and results return without model calls. {file.summary.running_jobs} unfinished requests will be marked interrupted and require explicit retry. Original prompts, cited passages and recorded results stay available.</p>
    <ArchiveVerification result={verification} />
    {reviewing && !error && <Loading label="Checking saved writer sources..." />}<ErrorNotice message={error} />
    <a className="button" href={file.download_url} download={file.filename}><Download size={16} />Download private archive</a><ErrorNotice message={action.error} />
    {restored ? <RestoreComplete result={restored} onOpen={onOpen} /> : <button className="button primary" aria-disabled={action.busy || reviewing} onClick={restore}>{action.busy ? 'Restoring saved history…' : 'Restore as new Stories'}</button>}
  </section>
}

function ArchiveCounts({ counts }: { counts: Record<string, number> }) {
  return <dl className="archive-counts">{[['stories', 'Stories'], ['branches', 'Branches'], ['nodes', 'Contributions'], ['assets', 'Library items'], ['asset_versions', 'Library versions'], ['writing_assets', 'Styles & recipes'], ['style_analysis_jobs', 'Sample analyses'], ['recipe_runs', 'Recipe runs'], ['text_edit_receipts', 'Applied text changes'], ['candidates', 'Writer drafts'], ['review_jobs', 'Reviews'], ['scene_runs', 'Scene plans'], ['side_turns', 'Side turns']].map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{(counts[key] ?? 0).toLocaleString()}</dd></div>)}</dl>
}

function RestoreComplete({ result, onOpen }: { result: RestoreResult; onOpen: (selection: Selection) => void }) {
  const notice = useRef<HTMLDivElement>(null)
  useEffect(() => { notice.current?.focus({ preventScroll: true }); notice.current?.scrollIntoView({ block: 'start' }) }, [])
  return <div ref={notice} tabIndex={-1} role="status" className="form-stack"><p>{result.story_ids.length} {result.story_ids.length === 1 ? 'Story' : 'Stories'} restored. Existing Stories are unchanged.</p>{result.selection.storyId && <button className="button primary" onClick={() => onOpen(result.selection as Selection)}>Open restored path</button>}</div>
}
