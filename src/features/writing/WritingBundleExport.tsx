import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { BundleResources } from './WritingBundlePreview'
import type { WritingResource } from './types'
import type { WritingBundle } from './bundleTypes'

export function WritingBundleExport({ resource, onClose }: { resource: WritingResource; onClose: () => void }) {
  const [samples, setSamples] = useState(false)
  const query = useQuery({ queryKey: ['writing-bundle-export', resource.id, samples], queryFn: () => api<WritingBundle>(`/writing-versions/${resource.id}/export`, { include_samples: samples }) })
  return <Modal open wide title={`Export ${resource.name}`} description={`Share version ${resource.number} and its explicit style dependency.`} onClose={onClose}><div className="dialog-body form-stack"><label className="check-row"><input type="checkbox" checked={samples} onChange={event => setSamples(event.target.checked)} />Include author-supplied writing samples</label><p className="subtle">Model assignments become named slots for the recipient to map locally. Model credentials, connection settings, Story text, and conversations are excluded.</p><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Preparing the bundle…" />}{query.data && <><BundleResources resources={query.data.resources} /><p className="subtle">{query.data.references.length} dependency mapping(s). {query.data.omitted_samples} sample(s) omitted.</p><details><summary>Inspect the export file</summary><pre className="writing-json">{JSON.stringify(query.data, null, 2)}</pre></details></>}</div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Close</button><button className="button primary" disabled={!query.data || query.isFetching || Boolean(query.error)} onClick={() => downloadBundle(query.data!, resource.name)}>Download writing bundle</button></footer></Modal>
}

function downloadBundle(bundle: WritingBundle, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url; link.download = (name.replace(/[^a-z0-9_-]+/gi, '-').slice(0, 80) || 'writing-resource') + '.writing.json'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
