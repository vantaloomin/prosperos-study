import { useRef, useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { AssetVersion } from '../../types'

interface Source {
  version_id: string; format: string; file_path: string; markdown: string | null
  sha256: string | null; published_sha256: string; missing: boolean; changed: boolean
  snapshot_hash: string | null; snapshot_needs_recovery: boolean; retained_file?: string | null
}
interface Props { asset: AssetVersion; text: string; sourceHash?: string | null; onUse: (text: string, hash: string | null) => void }

export function MarkdownSource({ asset, text, sourceHash, onUse }: Props) {
  const [source, setSource] = useState<Source | null>(null)
  const [review, setReview] = useState<Source | null>(null)
  const [previous, setPrevious] = useState<{ text: string; hash: string | null } | null>(null)
  const [copied, setCopied] = useState(false)
  const checkButton = useRef<HTMLButtonElement>(null)
  const action = useAction()
  const endpoint = `/library/${asset.asset_id}/markdown`
  const refresh = () => action.run(async () => { setSource(await api<Source>(`${endpoint}?version_id=${asset.id}`)); setCopied(false) })
  const recover = (target: 'working' | 'published') => action.run(async () => {
    const expected_hash = target === 'published' ? source!.snapshot_hash : null
    setSource(await api<Source>(`${endpoint}/recover`, { version_id: asset.id, target, expected_hash }))
    checkButton.current?.focus()
  })
  const copyPath = () => action.run(async () => { await navigator.clipboard.writeText(source!.file_path); setCopied(true) })
  const replaceFromFile = (file: Source) => {
    setPrevious({ text, hash: sourceHash ?? null })
    onUse(file.markdown!, file.sha256)
    setReview(null)
  }
  return <details className="markdown-source"><summary>Markdown source</summary><div className="form-stack">
    <p className="subtle">Edit this version’s working file in any text editor. Review the changes here, then save a new version. Each publication keeps the previous file and creates a new working copy.</p>
    <button ref={checkButton} className="button" aria-disabled={action.busy} onClick={refresh}>{action.busy ? 'Checking…' : 'Check Markdown file'}</button>
    <ErrorNotice message={action.error} />
    {source && <SourceDetails source={source} busy={action.busy} copied={copied} onCopy={copyPath} onReview={() => setReview(source)} onRecover={recover} />}
    {previous && <p className="subtle" role="status">File copied into the unpublished draft. <button className="text-button" onClick={(event) => { onUse(previous.text, previous.hash); setPrevious(null); event.currentTarget.closest('details')?.querySelector('summary')?.focus() }}>Undo replacement</button></p>}
    {sourceHash && sourceHash === source?.sha256 && <p className="subtle" role="status">This file version has been reviewed. Saving will publish the editor draft.</p>}
  </div>{review && <SourceReview source={review} draft={text} onUse={() => replaceFromFile(review)} onKeep={() => { onUse(text, review.sha256); setReview(null) }} onClose={() => setReview(null)} />}</details>
}

function SourceDetails({ source, busy, copied, onCopy, onReview, onRecover }: { source: Source; busy: boolean; copied: boolean; onCopy: () => void; onReview: () => void; onRecover: (target: 'working' | 'published') => void }) {
  return <div className="form-stack"><code className="source-path">{source.file_path}</code>
    <button className="text-button" onClick={onCopy}>{copied ? 'Path copied' : 'Copy file path'}</button>
    <p className="source-status" role="status">{sourceStatus(source)}</p>
    {source.missing ? <button className="button" aria-disabled={busy} onClick={() => onRecover('working')}>Recover missing working file</button> : <button className="button" disabled={busy || source.format !== 'plain-markdown'} onClick={onReview}>Review file against draft</button>}
    {source.snapshot_needs_recovery ? <><p className="subtle">The published file needs recovery. Its saved version remains intact; any changed file will be kept separately.</p><button className="button" aria-disabled={busy} onClick={() => onRecover('published')}>Recover published Markdown</button></> : <a className="text-button" href={`/api/versions/${source.version_id}/markdown`} download>Download published Markdown</a>}
    {source.retained_file && <p className="subtle">Previous file retained at <code className="source-path">{source.retained_file}</code></p>}
  </div>
}

function sourceStatus(source: Source) {
  if (source.format !== 'plain-markdown') return 'Legacy non-text metadata is preserved. Write Markdown prose in the editor before publishing a new version.'
  if (source.missing) return 'The working file is missing. Your published version is still available.'
  return source.changed ? 'The file contains unpublished edits. Stories still use their selected versions.' : 'The working file matches this published version.'
}

function SourceReview({ source, draft, onUse, onKeep, onClose }: { source: Source; draft: string; onUse: () => void; onKeep: () => void; onClose: () => void }) {
  return <Modal open wide title="Review Markdown changes" description="Choose which text to keep after reviewing the file. Both choices leave the file intact; nothing is published until you save a new version." onClose={onClose}>
    <div className="dialog-body"><div className="version-diff-columns source-preview">{[{ title: 'Current editor draft', text: draft }, { title: 'Markdown file', text: source.markdown ?? '' }].map((item) => <section key={item.title}><h3>{item.title}</h3><pre>{item.text.slice(0, 20000) || 'Empty Markdown document'}</pre>{item.text.length > 20000 && <p className="subtle">Preview shows the first 20,000 characters. The complete file is retained.</p>}</section>)}</div></div>
    <footer className="dialog-footer source-review-footer"><button className="text-button" onClick={onClose}>Cancel</button><button className="button" onClick={onKeep}>Use editor draft</button><button className="button primary" onClick={onUse}>Replace draft with file</button></footer>
  </Modal>
}
