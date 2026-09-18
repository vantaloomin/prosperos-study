import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { AssetContent, AssetVersion } from '../../types'
import { AuthoringDefaults, ModelChoices } from '../authoring/AuthoringModels'
import { RequestPreview } from '../authoring/AuthoringSetup'
import type { Preview, RequestBody, RunSummary } from '../authoring/types'
import type { ProfileList } from '../models/types'
import { readyProfiles } from '../models/profileReadiness'
import { EnrichmentResults } from './EnrichmentResults'

interface Props { name: string; content: AssetContent; asset?: AssetVersion; onChange: (patch: Partial<AssetContent>) => void; onClose: () => void }
interface Chunk { id: string; title: string; text: string; start: number; end: number }
interface Sources { items: Chunk[]; offset: number; next_offset: number | null; matches: number }
interface Prepared extends Preview { request: RequestBody }

export function CanonEnrichment(props: Props) {
  const [runId, setRunId] = useState<string | null>(null)
  return <Modal open wide title="Help Canon find its way back" description="Suggest search aids for selected Markdown passages. Review and edit them here; publishing a new version remains a separate step." onClose={props.onClose}>
    <div className="dialog-body form-stack">{runId ? <EnrichmentResults {...props} runId={runId} onNew={() => setRunId(null)} /> : <EnrichmentSetup {...props} onStarted={setRunId} />}
      <EnrichmentHistory asset={props.asset} onOpen={setRunId} />
    </div><footer className="dialog-footer"><button className="button" onClick={props.onClose}>Back to Canon draft</button></footer>
  </Modal>
}

function EnrichmentSetup({ name, content, asset, onStarted }: Props & { onStarted: (id: string) => void }) {
  const [draftId] = useState(() => crypto.randomUUID())
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<Chunk[]>([])
  const [compare, setCompare] = useState(false)
  const [profiles, setProfiles] = useState<string[]>([])
  const [direction, setDirection] = useState('')
  const [prepared, setPrepared] = useState<Prepared | null>(null)
  const action = useAction()
  const models = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const sources = useQuery({ queryKey: ['enrichment-sources', name, content, page], queryFn: () => api<Sources>('/canon/compile-preview', { name, content, offset: page * 12 }) })
  const change = (update: () => void) => { update(); setPrepared(null) }
  const toggle = (chunk: Chunk) => change(() => setSelected(selected.some(item => item.id === chunk.id) ? selected.filter(item => item.id !== chunk.id) : [...selected, chunk]))
  const preview = () => action.run(async () => setPrepared(await api<Prepared>('/canon/enrichment-preview', { name, content, selected: selected.map(item => item.id), draft_id: draftId, source_version_id: asset?.id, direction, profile_ids: profiles })))
  const start = () => action.run(async () => {
    if (!prepared) return
    const run = await api<{ id: string }>('/authoring', { ...prepared.request, operation_id: operationId(), preview_hash: prepared.preview_hash })
    onStarted(run.id)
  })
  const invalid = invalidRequest(selected.length, models.data, compare, profiles.length)
  return <><p className="subtle">Choose up to eight excerpts. Existing cues, including stale ones, are preserved. Suggestions can help a paraphrased query find exact prose; they cannot establish new facts.</p>
    <ErrorNotice message={sources.error?.message || models.error?.message || action.error} />
    <ExcerptChoices report={sources.data} pending={sources.isPending} fetching={sources.isFetching} content={content} selected={selected} onToggle={toggle} page={page} onPage={setPage} />
    <TextField label="Search guidance (optional)" value={direction} maxLength={10000} rows={2} onChange={event => change(() => setDirection(event.target.value))} placeholder="Include common alternate descriptions while preserving uncertainty…" />
    {models.data && <><ModelChoices profiles={models.data.profiles} selected={profiles} compare={compare} onMode={next => change(() => { setCompare(next); setProfiles([]) })} onChange={next => change(() => setProfiles(next))} /><AuthoringDefaults step="authoring-enrich" profiles={models.data.profiles} onChange={() => setPrepared(null)} /></>}
    <p className="subtle">One model request per profile for this batch. Previewing is local. Fewer excerpts can fit smaller models.</p>
    {prepared ? <RequestPreview preview={prepared} busy={action.busy} onStart={start} /> : <button className="button primary" disabled={action.busy || invalid} onClick={preview}>Preview search-aid requests</button>}
  </>
}

function ExcerptChoice({ chunk, selected, covered, full, onToggle }: { chunk: Chunk; selected: boolean; covered: boolean; full: boolean; onToggle: () => void }) {
  return <article className="prepared-card"><label className="check-row"><input type="checkbox" checked={selected} disabled={covered || (full && !selected)} onChange={onToggle} />{chunk.title} · characters {chunk.start + 1}–{chunk.end}</label>
    {covered && <p className="subtle">An existing cue covers this range and will be kept.</p>}<details><summary>Read original passage</summary><pre className="authoring-prose" tabIndex={0}>{chunk.text}</pre></details>
  </article>
}

function EnrichmentHistory({ asset, onOpen }: { asset?: AssetVersion; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const suffix = '?offset=' + page * 100 + (asset ? '&asset_id=' + asset.asset_id : '')
  const query = useQuery({ queryKey: ['authoring-history', suffix], queryFn: () => api<RunSummary[]>('/authoring' + suffix), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Saved search-aid requests</summary><div className="form-stack authoring-history"><ErrorNotice message={query.error?.message} />
    <p className="subtle">Page {page + 1} of Library assistant history. Only search-aid requests appear here. Applying checks the exact current overview and preserves existing cues.</p>
    {query.data?.filter(run => run.step === 'authoring-enrich').map(run => <button className="prompt-row" key={run.id} onClick={() => onOpen(run.id)}>{run.name} · {new Date(run.created_at).toLocaleString()}</button>)}
    <div className="import-downloads"><button className="button" disabled={!page || query.isFetching} onClick={() => setPage(page - 1)}>Newer requests</button><button className="button" disabled={query.data?.length !== 100 || query.isFetching} onClick={() => setPage(page + 1)}>Older requests</button></div>
  </div></details>
}

function invalidRequest(count: number, models: ProfileList | undefined, compare: boolean, profiles: number) {
  return !count || !models?.profiles.length || (compare && (profiles < 2 || profiles > 4))
}

function ExcerptChoices({ report, pending, fetching, content, selected, onToggle, page, onPage }: { report?: Sources; pending: boolean; fetching: boolean; content: AssetContent; selected: Chunk[]; onToggle: (chunk: Chunk) => void; page: number; onPage: (page: number) => void }) {
  const cues = content.canon_recall?.cues ?? []
  return <>{pending && <Loading label="Reading the Markdown…" />}<p role="status">{selected.length} excerpts selected</p>
    {report?.items.map(chunk => <ExcerptChoice key={chunk.id} chunk={chunk} selected={selected.some(item => item.id === chunk.id)} covered={cues.some(cue => cue.start < chunk.end && chunk.start < cue.end)} full={selected.length >= 8} onToggle={() => onToggle(chunk)} />)}
    {report && report.matches > 12 && <nav className="import-downloads" aria-label="Enrichment excerpt pages"><button className="button" disabled={!page || fetching} onClick={() => onPage(page - 1)}>Previous excerpts</button><button className="button" disabled={report.next_offset === null || fetching} onClick={() => onPage(page + 1)}>Next excerpts</button></nav>}
  </>
}
