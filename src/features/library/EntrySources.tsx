import { useRef, useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { AssetContent, AssetVersion } from '../../types'
import { emptyLore, type EntryFile, type LoreEntry } from './loreTypes'

interface Props { asset: AssetVersion; content: AssetContent; hashes: Record<string, string>; onUse: (content: AssetContent, hashes: Record<string, string>) => void }
interface Proposal extends EntryFile { entry: LoreEntry }
interface PreviousEntry { id: string; index: number; entry?: LoreEntry; markdown?: string; hash?: string }

export function EntrySources({ asset, content, hashes, onUse }: Props) {
  const [files, setFiles] = useState<EntryFile[] | null>(null)
  const [review, setReview] = useState<Proposal | null>(null)
  const [undo, setUndo] = useState<PreviousEntry | null>(null)
  const check = useRef<HTMLButtonElement>(null)
  const action = useAction()
  const endpoint = `/versions/${asset.id}`
  const refresh = () => action.run(async () => setFiles(await api<EntryFile[]>(`${endpoint}/entry-files`)))
  const inspect = (file: EntryFile) => action.run(async () => setReview(await api<Proposal>(`${endpoint}/entry-file?entry_id=${encodeURIComponent(file.entry_id)}`)))
  const recover = (file: EntryFile, target: 'working' | 'published') => action.run(async () => {
    await api(`${endpoint}/entry-recover?entry_id=${encodeURIComponent(file.entry_id)}`, { version_id: asset.id, target, expected_hash: target === 'working' ? null : file.snapshot_hash })
    setFiles(await api<EntryFile[]>(`${endpoint}/entry-files`)); check.current?.focus()
  })
  const useFile = () => {
    if (!review) return
    const definition = content.lore_definition ?? emptyLore
    const index = definition.entries.findIndex((entry) => entry.id === review.entry_id)
    setUndo({ id: review.entry_id, index, entry: definition.entries[index], markdown: content.lore_documents?.[review.entry_id], hash: hashes[review.entry_id] })
    onUse(replaceEntry(content, review.entry_id, review.entry, review.markdown!, index), { ...hashes, [review.entry_id]: review.sha256! })
    setReview(null)
  }
  const undoFile = () => {
    if (!undo) return
    const restoredHashes = { ...hashes }; delete restoredHashes[undo.id]
    if (undo.hash) restoredHashes[undo.id] = undo.hash
    onUse(replaceEntry(content, undo.id, undo.entry, undo.markdown, undo.index), restoredHashes)
    setUndo(null); check.current?.focus()
  }
  return <details className="markdown-source"><summary>Entry Markdown files</summary><div className="form-stack"><p className="subtle">Published entry files keep their metadata and prose together. Review external edits before saving a new version; previous working files stay intact.</p>
    <button ref={check} className="button" aria-disabled={action.busy} onClick={refresh}>Check entry files</button><ErrorNotice message={action.error} />
    {files && files.length === 0 && <p className="subtle">This published version has no entry files. New draft entries get files when you save.</p>}
    {files?.map((file) => <EntrySourceRow key={file.entry_id} file={file} reviewed={hashes[file.entry_id] === file.sha256} busy={action.busy} onReview={() => inspect(file)} onKeep={() => onUse(content, { ...hashes, [file.entry_id]: file.sha256! })} onRecover={(target) => recover(file, target)} />)}
    {undo && <p role="status">File copied into the draft. <button className="text-button" onClick={undoFile}>Undo entry replacement</button></p>}
  </div>{review && <EntryReview file={review} draft={content.lore_definition?.entries.find((item) => item.id === review.entry_id)} onClose={() => setReview(null)} onUse={useFile} onKeep={() => { onUse(content, { ...hashes, [review.entry_id]: review.sha256! }); setReview(null) }} />}</details>
}

function replaceEntry(content: AssetContent, id: string, entry: LoreEntry | undefined, markdown: string | undefined, index: number): AssetContent {
  const definition = content.lore_definition ?? emptyLore
  const entries = definition.entries.filter((item) => item.id !== id)
  if (entry) entries.splice(index < 0 ? entries.length : index, 0, entry)
  const documents = { ...content.lore_documents }; delete documents[id]
  if (markdown !== undefined) documents[id] = markdown
  return { ...content, lore_definition: { ...definition, entries }, lore_documents: documents }
}

function EntrySourceRow({ file, reviewed, busy, onReview, onKeep, onRecover }: { file: EntryFile; reviewed: boolean; busy: boolean; onReview: () => void; onKeep: () => void; onRecover: (target: 'working' | 'published') => void }) {
  return <section className="lore-result"><h4>{file.title}</h4><code className="source-path">{file.file_path}</code><p className="subtle">{fileStatus(file, reviewed)}</p>
    {file.markdown !== null && <details><summary>Inspect working Markdown</summary><pre className="lore-prose-preview">{file.markdown.slice(0, 24000)}</pre><p className="subtle">Showing at most 24,000 characters. Existing file bytes are retained when you keep the editor draft.</p></details>}
    {file.missing ? <button className="button" aria-disabled={busy} onClick={() => onRecover('working')}>Recover missing entry</button> : <><button className="button" aria-disabled={busy} onClick={onReview}>Review entry file</button>{file.changed && <button className="text-button" onClick={onKeep}>Keep editor entry and acknowledge file</button>}</>}
    {file.snapshot_needs_recovery ? <button className="button" aria-disabled={busy} onClick={() => onRecover('published')}>Recover entry snapshot</button> : <a className="text-button" href={`/api/versions/${file.version_id}/entry-download?entry_id=${encodeURIComponent(file.entry_id)}`} download>Download published entry</a>}
  </section>
}

function fileStatus(file: EntryFile, reviewed: boolean) {
  if (file.missing) return 'Working file missing. Recover it before publishing.'
  if (reviewed) return 'This file revision is acknowledged. Saving publishes the editor draft.'
  return file.changed ? 'Unpublished file edits need review. Stories retain their selected version.' : 'Working file matches this published entry.'
}

function EntryReview({ file, draft, onClose, onUse, onKeep }: { file: Proposal; draft?: LoreEntry; onClose: () => void; onUse: () => void; onKeep: () => void }) {
  return <Modal open wide title="Review entry changes" description="Compare the prose and rules. Neither choice publishes or overwrites the working file." onClose={onClose}>
    <div className="dialog-body version-diff-columns source-preview"><EntryComparison title="Editor draft" entry={draft} /><EntryComparison title="Entry file" entry={file.entry} /></div>
    <footer className="dialog-footer source-review-footer"><button className="text-button" onClick={onClose}>Cancel</button><button className="button" onClick={onKeep}>Use editor entry</button><button className="button primary" onClick={onUse}>Replace entry from file</button></footer>
  </Modal>
}

function EntryComparison({ title, entry }: { title: string; entry?: LoreEntry }) {
  if (!entry) return <section><h3>{title}</h3><p>Removed from draft.</p></section>
  const { text, ...rules } = entry
  return <section><h3>{title}</h3><h4>{entry.title}</h4><pre>{text.slice(0, 24000) || 'Empty entry prose'}</pre><details><summary>Entry rules</summary><pre>{JSON.stringify(rules, null, 2)}</pre></details><p className="subtle">Prose display limited to 24,000 characters; the complete entry is retained.</p></section>
}
