import { assetLabel } from './kinds'
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { AssetVersion } from '../../types'
import { AdoptionDialog } from './AdoptionDialog'
import { ImportChoiceEditor, ImportCompatibility } from './ImportFields'
import { ConvertedDocuments, SourceDownloads } from './ImportSources'
import { importChoices, publicationChoices, readImportFile, type ImportPreview } from './importTypes'

interface ImportProps {
  onClose: () => void; onPublishedClose?: () => void; initialImportId?: string; target?: AssetVersion
  focusOnClose?: () => HTMLElement | null; focusOnPublishedClose?: () => HTMLElement | null
}

export function LibraryImport({ onClose, onPublishedClose, initialImportId, target, focusOnClose, focusOnPublishedClose }: ImportProps) {
  const [id, setId] = usePersistent<string | null>(initialImportId ? `roleplay:library-import:${initialImportId}` : 'roleplay:library-import', initialImportId ?? null)
  useEffect(() => { rememberImport(id) }, [id])
  const [published, setPublished] = useState<AssetVersion[] | null>(null)
  const close = published ? onPublishedClose ?? onClose : onClose
  const finish = (versions: AssetVersion[]) => { setPublished(versions); setId(null) }
  return <Modal open wide title="Bring your world along" description="Import Markdown, a Character Card, or an SGC knowledge pack. Review the conversion, edit its fields, then choose what to publish." onClose={close} focusOnClose={published ? focusOnPublishedClose : focusOnClose}>
    {published ? <ImportSuccess versions={published} onClose={close} /> : <>
      <div className="dialog-body form-stack"><ImportUpload onReady={(preview) => setId(preview.id)} />
        {id && <ImportReview key={id} id={id} target={target} onPublished={finish} />}
      </div>{!id && <footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer>}
    </>}
  </Modal>
}

function rememberImport(id: string | null) {
  try { localStorage.setItem('roleplay:library-import', JSON.stringify(id)) } catch { /* The preserved source is still in the local database. */ }
}

function ImportUpload({ onReady }: { onReady: (preview: ImportPreview) => void }) {
  const action = useAction()
  const upload = (file?: File) => action.run(async () => {
    if (!file) return
    const source_base64 = await readImportFile(file)
    onReady(await api<ImportPreview>('/library-imports', { filename: file.name, source_base64 }))
  })
  return <section className="import-upload"><label className="field"><span>Choose Markdown, an SGC pack, or a JSON / PNG Character Card</span><input type="file" accept=".md,.markdown,.json,.png" aria-disabled={action.busy} onClick={(event) => { if (action.busy) event.preventDefault() }} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; void upload(file) }} /></label>
    <p className="subtle">Up to 10 MiB · UTF-8 text or PNG · Card V1, V2 or V3; SGC brain packs. Conversion stays on this device and uses no model. Choosing another file replaces the preview.</p>
    {action.busy && <Loading label="Preserving the source and preparing Markdown…" />}<ErrorNotice message={action.error} />
  </section>
}

function ImportReview({ id, target, onPublished }: { id: string; target?: AssetVersion; onPublished: (versions: AssetVersion[]) => void }) {
  const query = useQuery({ queryKey: ['library-import', id], queryFn: () => api<ImportPreview>(`/library-imports/${id}`) })
  return <><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Opening your import preview…" />}
    {query.data && <ImportPublication preview={query.data} target={target} onPublished={onPublished} />}</>
}

function ImportPublication({ preview, target, onPublished }: { preview: ImportPreview; target?: AssetVersion; onPublished: (versions: AssetVersion[]) => void }) {
  const key = `roleplay:library-import-draft:${preview.id}`
  const [draft, setDraft] = usePersistent(key, { choices: importChoices(preview, target), reviewed: false, operation: operationId() })
  const [inspect, setInspect] = useState(false)
  const [uploads, setUploads] = useState<Record<string, boolean>>({})
  const uploading = Object.values(uploads).some(Boolean)
  const heading = useRef<HTMLHeadingElement>(null)
  const assets = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const action = useAction()
  useEffect(() => { heading.current?.focus() }, [])
  const selected = publicationChoices(draft.choices)
  const publish = () => action.run(async () => {
    const result = await api<{ versions: AssetVersion[] }>(`/library-imports/${preview.id}/publish`, {
      operation_id: draft.operation, source_sha256: preview.source_sha256, reviewed_compatibility: draft.reviewed, choices: selected })
    localStorage.removeItem(key)
    onPublished(result.versions)
  })
  return <section className="import-review form-stack"><h3 ref={heading} tabIndex={-1}>{preview.filename}</h3>
    <p className="subtle">{importFormat(preview)} · Preserved Markdown files: {preview.files.length}</p>
    <SourceDownloads id={preview.id} /><button className="button" onClick={() => setInspect(true)}>Inspect converted Markdown</button>
    <ImportCompatibility preview={preview} /><ErrorNotice message={assets.error?.message} />
    {draft.choices.map((choice, index) => <ImportChoiceEditor key={choice.part} choice={choice} assets={assets.data ?? []} onBusy={(busy) => setUploads((previous) => previous[choice.part] === busy ? previous : { ...previous, [choice.part]: busy })} onChange={(patch) => { action.clearError(); setDraft({ ...draft, operation: operationId(), choices: draft.choices.map((item, at) => at === index ? { ...item, ...patch } : item) }) }} />)}
    <label className="check-row"><input type="checkbox" checked={draft.reviewed} onChange={(event) => setDraft({ ...draft, reviewed: event.target.checked })} />I reviewed the active fields and the material kept only as reference.</label>
    <ErrorNotice message={action.error} /><div className="import-publish"><p className="subtle">Selected for publication: {selected.length}. Existing Stories keep their current versions.</p><PublicationButton reviewed={draft.reviewed} count={selected.length} busy={action.busy} uploading={uploading} onPublish={publish} /></div>
    {inspect && <ConvertedDocuments id={preview.id} onClose={() => setInspect(false)} />}
  </section>
}

function ImportSuccess({ versions, onClose }: { versions: AssetVersion[]; onClose: () => void }) {
  const [adoption, setAdoption] = useState<AssetVersion | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  return <><div className="dialog-body form-stack"><h3 ref={heading} tabIndex={-1}>Ready in your Library</h3><p className="subtle">Published sources and earlier versions are preserved. Story updates are a separate, reviewed action.</p>
    {versions.map((version) => <section className="import-choice" key={version.id}><h3>{version.name} · v{version.number}</h3><span className="eyebrow">{assetLabel(version.kind)}</span><button className="button" onClick={() => setAdoption(version)}>Review Story updates for {version.name}</button></section>)}
  </div><footer className="dialog-footer"><button className="button primary" onClick={onClose}>Back to Library</button></footer>
    {adoption && <AdoptionDialog version={adoption} onClose={() => setAdoption(null)} />}
  </>
}

function PublicationButton({ reviewed, count, busy, uploading, onPublish }: { reviewed: boolean; count: number; busy: boolean; uploading: boolean; onPublish: () => void }) {
  return <button className="button primary" disabled={uploading || !reviewed || !count} aria-disabled={busy || uploading} onClick={onPublish}>{busy ? 'Publishing…' : 'Publish selected items'}</button>
}

function importFormat(preview: ImportPreview) {
  if (preview.format === 'sgc-brain') return 'SGC knowledge pack'
  return preview.card_version ? 'Character Card ' + preview.card_version.toUpperCase() : 'Markdown Canon collection'
}
