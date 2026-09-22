import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { BundleMappingsView, BundleResources } from './WritingBundlePreview'
import type { WritingResource } from './types'
import type { BundleMappings, BundleReport } from './bundleTypes'

const MAX_BYTES = 8 * 1024 * 1024

export function WritingBundleImport({ onClose, onImported }: { onClose: () => void; onImported: (resource: WritingResource) => void }) {
  const [source, setSource] = useState('')
  const [mappings, setMappings] = useState<BundleMappings>({})
  const [review, setReview] = useState<{ report: BundleReport; input: string } | null>(null)
  const operation = useRef({ id: operationId(), input: '' })
  const action = useAction()
  const input = JSON.stringify([source, mappings])
  const current = review?.input === input
  const load = (file?: File) => action.run(async () => {
    if (!file) return
    if (file.size > MAX_BYTES) throw new Error('Writing bundles are limited to 8 MiB.')
    setSource(await file.text()); setMappings({}); setReview(null)
  })
  const preview = () => action.run(async () => {
    if (new Blob([source]).size > MAX_BYTES) throw new Error('Writing bundles are limited to 8 MiB.')
    const report = await api<BundleReport>('/writing-bundles/preview', { document: JSON.parse(source), mappings })
    setReview({ report, input })
  })
  const save = () => action.run(async () => {
    if (!review || !current || !review.report.can_import) throw new Error('Preview a compatible import first.')
    const body = { document: JSON.parse(source), mappings, preview_fingerprint: review.report.fingerprint }
    const encoded = JSON.stringify(body)
    if (operation.current.input !== encoded) operation.current = { id: operationId(), input: encoded }
    const result = await api<{ root_version_id: string; resources: WritingResource[] }>('/writing-bundles/import', { ...body, operation_id: operation.current.id })
    onImported(result.resources.find(item => item.id === result.root_version_id)!)
  })
  return <Modal open wide title="Import writing tools" description="Inspect the resources and choose their local dependencies before adding them to your Library." onClose={onClose}><div className="dialog-body form-stack"><label className="field"><span>Writing bundle file</span><input aria-label="Writing bundle file" type="file" accept=".json,application/json" onChange={event => void load(event.target.files?.[0])} /></label><details><summary>Paste or edit bundle JSON</summary><TextField label="Writing bundle JSON" rows={10} value={source} onChange={event => { setSource(event.target.value); setReview(null) }} /></details><button className="button" disabled={!source.trim() || action.busy} onClick={preview}>Preview import</button><ImportReview review={review} current={current} mappings={mappings} onMappings={setMappings} /><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Importing starts no model calls and changes no Story defaults.</span><button className="button primary" disabled={!current || !review?.report.can_import || action.busy} onClick={save}>Add to Library</button></footer></Modal>
}

function ImportReview({ review, current, mappings, onMappings }: { review: { report: BundleReport } | null; current: boolean; mappings: BundleMappings; onMappings: (value: BundleMappings) => void }) {
  if (!review) return null
  return <><BundleResources resources={review.report.resources} /><BundleMappingsView report={review.report} value={mappings} onChange={onMappings} />{!current && <p role="status">Mappings changed. Preview again to validate these choices.</p>}{current && review.report.errors.length > 0 && <div role="status"><p>Before importing:</p><ul>{review.report.errors.map(error => <li key={error}>{error}</li>)}</ul></div>}<p className="subtle">{review.report.omitted_samples} sample(s) were omitted by the exporter. {review.report.activation}</p></>
}
