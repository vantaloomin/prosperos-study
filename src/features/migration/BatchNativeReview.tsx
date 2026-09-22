import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { ArchiveCounts, type ArchiveFile } from '../export/Archives'
import { ArchiveVerification } from '../export/ArchiveVerification'
import { BundleMappingsView, BundleResources } from '../writing/WritingBundlePreview'
import type { BundleMappings, BundleReport } from '../writing/bundleTypes'
import type { BatchItem, BatchPublisher } from './batchTypes'

function NativeDecision({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <label className="field"><span>Native file duplicate decision</span><select aria-label="Native file duplicate decision" value={value} onChange={event => onChange(event.target.value)}><option value="skip">Skip a matching completed migration import</option><option value="new">Deliberately create another copy</option></select><small>Native-file matches use saved migration receipts. Older standalone bundle imports did not retain their original files and cannot be identified from a filename.</small></label>
}

export function BatchArchiveReview({ file, publish }: { file: ArchiveFile; publish: BatchPublisher }) {
  const [reviewed, setReviewed] = useState(false), [decision, setDecision] = useState('skip')
  const action = useAction()
  return <section className="form-stack"><h4>Review private archive</h4><p>{file.summary.title}</p><ArchiveCounts counts={file.summary.counts} /><p>{file.summary.include_sidebar ? 'Includes private sidebar conversations and saved unsent questions.' : 'Private sidebar material is excluded.'}</p><ul>{file.summary.stories.map(story => <li key={story.id}>{story.title}</li>)}</ul><p>Restoration creates new copies, preserving shared links and version history. Current Stories, primary model and backup schedule stay unchanged. Imported credentials are not restored; unfinished work needs explicit retry.</p><ArchiveVerification result={file.summary.writer_verification} /><NativeDecision value={decision} onChange={value => { setDecision(value); setReviewed(false) }} />
    <label className="check-row"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the archive scope, private material and saved-source verification.</label><ErrorNotice message={action.error} /><button className="button primary" disabled={!reviewed || action.busy} onClick={() => action.run(async () => { await publish({ sha256: file.sha256, duplicate_action: decision }) })}>Restore reviewed archive as new copies</button>
  </section>
}

export function BatchBundleReview({ item, publish }: { item: BatchItem; publish: BatchPublisher }) {
  const [mappings, setMappings] = usePersistent<BundleMappings>(`roleplay:batch-bundle:${item.id}`, {})
  const [reviewed, setReviewed] = useState(false), [decision, setDecision] = useState('skip')
  const query = useQuery({ queryKey: ['batch-bundle-preview', item.id, mappings], queryFn: () => api<BundleReport>(`/migration/batch-items/${item.id}/bundle-preview`, { mappings }), retry: false })
  const action = useAction()
  const save = () => action.run(async () => { if (query.data) await publish({ mappings, preview_fingerprint: query.data.fingerprint, duplicate_action: decision }) })
  return <section className="form-stack"><h4>Review native writing bundle</h4>{query.isFetching && <Loading label="Checking resources and local dependencies…" />}<ErrorNotice message={query.error?.message || action.error} />{query.data && <><BundleResources resources={query.data.resources} /><BundleMappingsView report={query.data} value={mappings} onChange={value => { setMappings(value); setReviewed(false) }} /><ul>{query.data.errors.map(error => <li key={error}>{error}</li>)}</ul><p>{query.data.activation} {query.data.omitted_samples} samples were omitted by the exporter.</p></>}
    <NativeDecision value={decision} onChange={value => { setDecision(value); setReviewed(false) }} /><label className="check-row"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the native resources, unsupported fields and local dependency mappings.</label><button className="button primary" disabled={!reviewed || !query.data?.can_import || query.isFetching || action.busy} onClick={save}>Import reviewed writing bundle</button>
  </section>
}
