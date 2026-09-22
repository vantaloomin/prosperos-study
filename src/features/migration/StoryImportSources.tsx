import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { TranscriptDownloads } from './TranscriptReview'
import { roleLabels, type TranscriptChoice, type TranscriptPreview } from './transcriptTypes'

interface SourceOrigin { id: string; import_id: string; filename: string; receipt: { title: string; selections: TranscriptChoice[] } }

export function StoryImportSources({ storyId }: { storyId: string }) {
  const [open, setOpen] = useState(false)
  const [source, setSource] = useState<SourceOrigin | null>(null)
  const query = useQuery({ queryKey: ['story-imports', storyId], queryFn: () => api<SourceOrigin[]>(`/stories/${storyId}/imports`), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Preserved migration sources</summary>{open && <div className="form-stack"><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Opening import provenance…" />}{query.data?.length === 0 && <p className="subtle">This Story has no imported transcript.</p>}{query.data?.map(item => <section key={item.id}><h4>{item.filename}</h4><TranscriptDownloads id={item.import_id} /><button className="button" onClick={() => setSource(item)}>Inspect original messages and chosen mapping</button></section>)}</div>}{source && <SourceInspection source={source} onClose={() => setSource(null)} />}</details>
}

function SourceInspection({ source, onClose }: { source: SourceOrigin; onClose: () => void }) {
  const [page, setPage] = useState(0)
  const query = useQuery({ queryKey: ['transcript-import', source.import_id], queryFn: () => api<TranscriptPreview>(`/migration/transcripts/${source.import_id}`) })
  const choices = new Map(source.receipt.selections.map(item => [item.index, item]))
  return <Modal open wide title="Original transcript and mapping" description="The preserved source and choices made when this Story was imported. Later writing remains separate." onClose={onClose}><div className="dialog-body form-stack"><TranscriptDownloads id={source.import_id} /><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}{query.data?.messages.slice(page * 20, (page + 1) * 20).map(message => {
    const selected = choices.get(message.index)
    return <article key={message.index} className="migration-message"><h4>Message {message.index + 1} · {message.speaker}</h4><p className="subtle">{selected ? `${roleLabels[selected.role]} · ${selected.variant ? `alternative ${selected.variant}` : 'current source message'}` : 'Kept as reference only'} · Source role: {message.source_role}{message.timestamp ? ` · ${message.timestamp}` : ''}</p>{message.variants.map((text, index) => <details key={index} open={index === (selected?.variant ?? 0)}><summary>{index === 0 ? 'Current source message' : `Alternative ${index}`}</summary><pre tabIndex={0} className="migration-prose">{text}</pre></details>)}</article>
  })}<nav className="migration-actions" aria-label="Original transcript pages"><button className="button" disabled={!page} onClick={() => setPage(page - 1)}>Previous messages</button><button className="button" disabled={(page + 1) * 20 >= (query.data?.messages.length ?? 0)} onClick={() => setPage(page + 1)}>Next messages</button></nav></div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer></Modal>
}
