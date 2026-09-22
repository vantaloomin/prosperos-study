import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Selection } from '../../types'
import { readImportFile } from '../library/importTypes'
import { TranscriptReview } from './TranscriptReview'
import type { TranscriptPreview } from './transcriptTypes'
import { PresetMigration } from './PresetMigration'
import { BatchMigration } from './BatchMigration'

export function Migration({ onClose, onOpen }: { onClose: () => void; onOpen: (selection: Selection) => void }) {
  const [kind, setKind] = usePersistent('roleplay:migration-kind', 'batch')
  return <Modal open wide title="Migrate your writing" description="Review source material and compatibility before creating Stories or writing resources." onClose={onClose}><div className="dialog-body form-stack"><div className="tabs migration-tabs" aria-label="Migration type"><button aria-pressed={kind === 'batch'} onClick={() => setKind('batch')}>Mixed files</button><button aria-pressed={kind === 'transcript'} onClick={() => setKind('transcript')}>Transcripts</button><button aria-pressed={kind === 'preset'} onClick={() => setKind('preset')}>Generation presets</button></div><MigrationView kind={kind} onOpen={selection => { onClose(); onOpen(selection) }} /></div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer></Modal>
}

function MigrationView({ kind, onOpen }: { kind: string; onOpen: (selection: Selection) => void }) {
  if (kind === 'preset') return <PresetMigration />
  if (kind === 'transcript') return <TranscriptMigration onOpen={onOpen} />
  return <BatchMigration onOpen={onOpen} />
}

function TranscriptMigration({ onOpen }: { onOpen: (selection: Selection) => void }) {
  const [id, setId] = usePersistent<string | null>('roleplay:transcript-import', null)
  const query = useQuery({ queryKey: ['transcript-import', id], queryFn: () => api<TranscriptPreview>(`/migration/transcripts/${id}`), enabled: !!id })
  const history = useQuery({ queryKey: ['transcript-imports'], queryFn: () => api<{ id: string; filename: string; created_at: string; imported_stories: number }[]>('/migration/transcripts') })
  const action = useAction()
  const upload = (file?: File) => action.run(async () => {
    if (!file) return
    const source_base64 = await readImportFile(file)
    const preview = await api<TranscriptPreview>('/migration/transcripts', { filename: file.name, source_base64 })
    setId(preview.id)
  })
  return <div className="form-stack">
    <label className="field"><span>Choose a transcript</span><input type="file" accept=".jsonl,.json,.txt,.md,.markdown" disabled={action.busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; void upload(file) }} /></label><p className="subtle">SillyTavern JSONL, text-only role/content JSON, UTF-8 text or Markdown · Up to 10 MiB and 2,000 messages. Text speaker labels and Markdown headings need your explicit role mapping. Conversion stays local and uses no model.</p>
    <details><summary>Recent transcript sources</summary><ErrorNotice message={history.error?.message} />{history.data?.map(item => <button className="text-button migration-history" key={item.id} onClick={() => setId(item.id)}>{item.filename} · {item.imported_stories} imported Stories · {new Date(item.created_at).toLocaleString()}</button>)}</details>
    <ErrorNotice message={action.error || query.error?.message} />{(action.busy || (id && query.isPending)) && <Loading label="Preparing your transcript review…" />}
    {!action.busy && query.data && <TranscriptReview key={query.data.id} preview={query.data} onOpen={onOpen} />}
  </div>
}
