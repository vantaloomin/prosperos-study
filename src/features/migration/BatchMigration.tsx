import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { readImportFile } from '../library/importTypes'
import type { Selection } from '../../types'
import { BatchQueue } from './BatchQueue'
import type { MigrationBatch } from './batchTypes'

async function batchFiles(files: File[]) {
  if (!files.length || files.length > 20) throw new Error('Choose 1–20 files for one migration batch.')
  if (files.reduce((size, file) => size + file.size, 0) > 32 * 1024 * 1024) throw new Error('One batch can contain up to 32 MiB of original files.')
  return Promise.all(files.map(async file => {
    try { return { filename: file.name, source_base64: await readImportFile(file) } }
    catch (error) { return { filename: file.name, source_base64: '', read_error: error instanceof Error ? error.message.slice(0, 200) : 'This file could not be read.' } }
  }))
}

export function BatchMigration({ onOpen }: { onOpen: (selection: Selection) => void }) {
  const [id, setId] = usePersistent<string | null>('roleplay:migration-batch', null)
  const query = useQuery({ queryKey: ['migration-batch', id], queryFn: () => api<MigrationBatch>(`/migration/batches/${id}`), enabled: !!id })
  const history = useQuery({ queryKey: ['migration-batches'], queryFn: () => api<{ id: string; created_at: string; items: number; finished: number }[]>('/migration/batches') })
  const operation = useRef({ input: '', id: operationId() })
  const action = useAction()
  const upload = (files: File[]) => action.run(async () => {
    const source = await batchFiles(files), input = JSON.stringify(source)
    if (operation.current.input !== input) operation.current = { input, id: operationId() }
    const batch = await api<MigrationBatch>('/migration/batches', { operation_id: operation.current.id, files: source })
    setId(batch.id); operation.current = { input: '', id: operationId() }
  })
  return <div className="form-stack"><label className="field"><span>Choose migration files</span><input aria-label="Choose migration files" type="file" multiple disabled={action.busy} onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = ''; if (files.length) void upload(files) }} /></label>
    <p className="subtle">Up to 20 files, 10 MiB each and 32 MiB total. Presets allow 1 MiB; native writing bundles allow 8 MiB. Larger Study archives can use Settings → Backups & recovery. Content detection, conversion and review stay local.</p>
    <details><summary>Recent migration batches</summary><ErrorNotice message={history.error?.message} />{history.data?.map(batch => <button className="text-button migration-history" key={batch.id} onClick={() => setId(batch.id)}>{new Date(batch.created_at).toLocaleString()} · {batch.finished}/{batch.items} resolved files</button>)}</details>
    <ErrorNotice message={action.error || query.error?.message} />{(action.busy || (!!id && query.isPending)) && <Loading label="Inspecting your migration files…" />}
    {!action.busy && query.data && <BatchQueue key={query.data.id} batch={query.data} onOpen={onOpen} />}
  </div>
}
