import { lazy, Suspense, useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { AssetContent, AssetVersion } from '../../types'
import { CanonPackExport } from './CanonPackExport'

const CanonEnrichment = lazy(() => import('./CanonEnrichment').then(module => ({ default: module.CanonEnrichment })))
const CanonCueManager = lazy(() => import('./CanonCueManager').then(module => ({ default: module.CanonCueManager })))

export type { CanonCue, CanonPolicy } from './canonCueTypes'
interface Props { name: string; content: AssetContent; asset?: AssetVersion; onChange: (patch: Partial<AssetContent>) => void }
interface Chunk { id: string; title: string; text: string; start: number; end: number; search_cues: { summary: string; topics: string[]; aliases: string[] } }
interface Preview { chunks: number; active_cues: number; stale_cues: number; matches: number; offset: number; next_offset: number | null; items: Chunk[] }

export function CanonMemory({ name, content, asset, onChange }: Props) {
  const [managing, setManaging] = useState(false)
  const [preview, setPreview] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const policy = content.canon_recall ?? {}
  return <details className="advanced-settings"><summary>Recall &amp; sharing</summary><div className="form-stack character-advanced">
    <label className="field"><span>Overview in Long story mode</span><select value={policy.mode ?? 'full'} onChange={(event) => onChange({ canon_recall: { ...policy, mode: event.target.value as 'full' | 'relevant' } })}>
      <option value="full">Always include the complete overview</option><option value="relevant">Recall relevant excerpts when space is limited</option>
    </select></label>
    <p className="subtle">Full history keeps the complete overview. In Long story, relevant recall can make room for recent prose in writing, scene work and reviews. Required guidance belongs in the complete overview or an explicit required entry. Entry activation and chance rules still apply separately.</p>
    <button className="button" onClick={() => setPreview(true)}>Preview Canon recall</button>
    <button className="button" disabled={!content.text} onClick={() => setEnriching(true)}>Suggest search aids</button>
    <SavedCueControls content={content} onManage={() => setManaging(true)} />
    {asset && <button className="text-button" onClick={() => setExporting(true)}>Export published v{asset.number} as an SGC pack</button>}
  </div>{preview && <CanonPreview name={name} content={content} onClose={() => setPreview(false)} />}
    {managing && <Suspense fallback={<p className="subtle">Opening saved aids…</p>}><CanonCueManager content={content} asset={asset} onChange={onChange} onClose={() => setManaging(false)} /></Suspense>}
    {enriching && <Suspense fallback={<p className="subtle">Opening search-aid review…</p>}><CanonEnrichment name={name} content={content} asset={asset} onChange={onChange} onClose={() => setEnriching(false)} /></Suspense>}
    {exporting && asset && <CanonPackExport asset={asset} onClose={() => setExporting(false)} />}
  </details>
}

function SavedCueControls({ content, onManage }: { content: AssetContent; onManage: () => void }) {
  const count = content.canon_recall?.cues?.length ?? 0
  return <><p className="subtle">{count} saved search aids. Aids whose source changed stay inactive until the original source is restored. Review, edit or remove them below.</p>
    <button className="button" onClick={onManage}>Manage saved search aids</button>
  </>
}

function CanonPreview({ name, content, onClose }: { name: string; content: AssetContent; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [usedQuery, setUsedQuery] = useState('')
  const [report, setReport] = useState<Preview | null>(null)
  const action = useAction()
  const read = (offset = 0, search = query) => action.run(async () => {
    const result = await api<Preview>('/canon/compile-preview', { name, content, query: search, offset })
    setReport(result); setUsedQuery(search)
  })
  return <Modal open wide title="Canon recall preview" description="Inspect the current editor draft. This local preview uses no model and changes no Story or published version." onClose={onClose}>
    <div className="dialog-body form-stack"><form className="form-stack" onSubmit={(event) => { event.preventDefault(); void read() }}>
      <label className="field"><span>Search this Canon draft</span><input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={4000} placeholder="A place, name, concept, or alias…" /></label>
      <button className="button" disabled={action.busy} type="submit">{action.busy ? 'Compiling…' : query.trim() ? 'Search excerpts' : 'Browse all excerpts'}</button>
    </form><ErrorNotice message={action.error} />{report && <>
      <p role="status">{report.chunks} compiled excerpts · {report.active_cues} active search cues · {previewMatches(report.matches, usedQuery)}</p>
      {report.stale_cues > 0 && <p className="subtle">{report.stale_cues} cues no longer match their exact source spans. They are preserved for review, but are excluded from retrieval. Current prose remains searchable.</p>}
      <p className="subtle">The writer receives selected exact prose, not the search cues. Collection attachment, Story settings and the request budget decide what is actually sent.</p>
      {report.items.map((item) => <article className="import-choice" key={item.id}><h3>{item.title}</h3><small>Characters {item.start}–{item.end}</small><pre className="import-document" tabIndex={0}>{item.text}</pre>
        <details><summary>Search cues for this excerpt</summary><p>{item.search_cues.summary || 'No summary cue.'}</p><p>{[...item.search_cues.topics, ...item.search_cues.aliases].join(' · ') || 'No topics or aliases.'}</p></details>
      </article>)}
      {report.matches > 12 && <nav className="import-downloads" aria-label="Canon excerpt pages"><button className="button" disabled={action.busy || report.offset === 0} onClick={() => read(Math.max(0, report.offset - 12), usedQuery)}>Previous excerpts</button><button className="button" disabled={action.busy || report.next_offset === null} onClick={() => read(report.next_offset!, usedQuery)}>Next excerpts</button></nav>}
    </>}</div><footer className="dialog-footer"><button className="button primary" onClick={onClose}>Done</button></footer>
  </Modal>
}


function previewMatches(count: number, query: string) {
  if (!query) return count + (count === 1 ? ' available excerpt' : ' available excerpts')
  return count + (count === 1 ? ' match' : ' matches') + ' (up to 16)'
}
