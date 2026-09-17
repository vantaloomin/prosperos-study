import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import type { AssetVersion } from '../../types'
import type { ImportPreview } from './importTypes'

export function SourceDownloads({ id }: { id: string }) {
  return <div className="import-downloads"><a className="text-button" href={`/api/library-imports/${id}/original`} download>Download original file</a><a className="text-button" href={`/api/library-imports/${id}/package`} download>Download Markdown package</a></div>
}

export function ConvertedDocuments({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['library-import', id], queryFn: () => api<ImportPreview>(`/library-imports/${id}`) })
  return <Modal open wide title="Converted source documents" description="Preserved reference material. These files do not automatically become prompts, active Canon entries or Story events." onClose={onClose}>
    <div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />
      {query.isPending && <Loading label="Opening the converted documents…" />}
      {query.data && <DocumentBrowser preview={query.data} />}<SourceDownloads id={id} />
    </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer>
  </Modal>
}

function DocumentBrowser({ preview }: { preview: ImportPreview }) {
  const [search, setSearch] = useState('')
  const [path, setPath] = useState(preview.files[0]?.path ?? '')
  const matches = preview.files.filter((file) => file.path.toLowerCase().includes(search.toLowerCase()))
  const visible = matches.slice(0, 80)
  const query = useQuery({ queryKey: ['library-import-document', preview.id, path], queryFn: () => api<{ markdown: string }>(`/library-imports/${preview.id}/document?path=${encodeURIComponent(path)}`), enabled: !!path })
  return <><label className="field"><span>Find a converted document</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Entry number, greeting, notes…" /></label>
    <p className="subtle">{matches.length} matching documents{matches.length > 80 ? ' · showing the first 80; narrow your search to see others' : ''}.</p>
    <div className="import-document-list" aria-label="Converted files">{visible.map((file) => <button className="text-button" key={file.path} aria-pressed={path === file.path} onClick={() => setPath(file.path)}>{file.path}</button>)}</div>
    <h3 className="source-path">{path}</h3><ErrorNotice message={query.error?.message} />
    {query.isPending ? <Loading label="Reading Markdown…" /> : <pre className="import-document" tabIndex={0}>{query.data?.markdown.slice(0, 20000)}</pre>}
    {(query.data?.markdown.length ?? 0) > 20000 && <p className="subtle">Showing the first 20,000 characters. Download the package for the complete document.</p>}
  </>
}

export function ImportedSources({ asset }: { asset?: AssetVersion }) {
  return asset ? <VersionSources versionId={asset.id} /> : null
}

function VersionSources({ versionId }: { versionId: string }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const query = useQuery({ queryKey: ['asset-imports', versionId], queryFn: () => api<{ id: string; filename: string; part: string }[]>(`/versions/${versionId}/imports`), enabled: open })
  return <details className="markdown-source" onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Preserved import sources</summary>
    {open && <div className="form-stack"><p className="subtle">Original files and their converted Markdown remain available after later edits. Preserved instructions and entry rules are reference material, separate from this version’s active fields.</p>
      <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Checking source imports…" />}
      {query.data?.length === 0 && <p className="subtle">This version has no imported source files.</p>}
      {query.data?.map((source) => <section key={`${source.id}-${source.part}`}><h4>{source.filename}</h4><SourceDownloads id={source.id} /><button className="text-button" onClick={() => setSelected(source.id)}>Inspect converted Markdown</button></section>)}
    </div>}{selected && <ConvertedDocuments id={selected} onClose={() => setSelected(null)} />}
  </details>
}
