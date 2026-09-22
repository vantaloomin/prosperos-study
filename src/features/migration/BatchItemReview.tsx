import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Selection } from '../../types'
import { ImportPublication } from '../library/LibraryImport'
import type { ImportPreview, ImportResult } from '../library/importTypes'
import type { ArchiveFile } from '../export/Archives'
import { TranscriptReview } from './TranscriptReview'
import { PresetReview } from './PresetReview'
import { BatchArchiveReview, BatchBundleReview } from './BatchNativeReview'
import type { PresetPreview, PresetResult } from './presetTypes'
import type { TranscriptPreview, TranscriptResult } from './transcriptTypes'
import type { BatchItem } from './batchTypes'

type Preview = ImportPreview | PresetPreview | TranscriptPreview | ArchiveFile

export function BatchItemReview({ item, onOpen, onPublishing }: { item: BatchItem; onOpen: (selection: Selection) => void; onPublishing: (busy: boolean) => void }) {
  const query = useQuery({ queryKey: ['batch-item-preview', item.id, item.import_id], queryFn: () => api<Preview>(`/migration/batch-items/${item.id}/preview`), enabled: item.kind !== 'writing-bundle' })
  const cache = useQueryClient()
  const publish = async (choices: object) => {
    onPublishing(true)
    try { return (await api<BatchItem>(`/migration/batch-items/${item.id}/publish`, { expected_revision: item.revision, choices })).result }
    finally { await cache.invalidateQueries({ queryKey: ['migration-batch', item.batch_id] }); onPublishing(false) }
  }
  const key = `roleplay:batch-draft:${item.id}:${item.import_id}`
  if (item.kind === 'writing-bundle') return <BatchBundleReview item={item} publish={publish} />
  if (query.isPending) return <Loading label="Opening this source review…" />
  if (!query.data) return <ErrorNotice message={query.error?.message} />
  const duplicates = item.batch_duplicates.filter(match => match.kind === item.kind)
  if (item.kind === 'library') return <ImportPublication preview={query.data as ImportPreview} draftKey={key} batchDuplicateParts={duplicates.flatMap(match => match.parts)} publishChoices={async choices => await publish(choices) as ImportResult} onPublished={() => {}} />
  if (item.kind === 'transcript') return <TranscriptReview preview={query.data as TranscriptPreview} draftKey={key} hasBatchDuplicate={!!duplicates.length} publishChoices={async choices => await publish(choices) as TranscriptResult} onOpen={onOpen} />
  if (item.kind === 'preset') return <PresetReview preview={query.data as PresetPreview} draftKey={key} hasBatchDuplicate={!!duplicates.length} publishChoices={async choices => await publish(choices) as PresetResult} />
  return <BatchArchiveReview file={query.data as ArchiveFile} publish={publish} />
}
