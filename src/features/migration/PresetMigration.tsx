import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { readImportFile } from '../library/importTypes'
import { PresetReview } from './PresetReview'
import type { PresetPreview } from './presetTypes'

export function PresetMigration() {
  const [id, setId] = usePersistent<string | null>('roleplay:preset-import', null)
  const query = useQuery({ queryKey: ['preset-import', id], queryFn: () => api<PresetPreview>(`/migration/presets/${id}`), enabled: !!id })
  const history = useQuery({ queryKey: ['preset-imports'], queryFn: () => api<{ id: string; filename: string; published_versions: number }[]>('/migration/presets') })
  const action = useAction()
  const upload = (file?: File) => action.run(async () => {
    if (!file) return
    if (file.size > 1024 * 1024) throw new Error('Generation presets are limited to 1 MiB.')
    const preview = await api<PresetPreview>('/migration/presets', { filename: file.name, source_base64: await readImportFile(file) })
    setId(preview.id)
  })
  return <div className="form-stack"><label className="field"><span>Choose a generation preset</span><input type="file" accept=".json,.preset" disabled={action.busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; void upload(file) }} /></label><p className="subtle">SillyTavern text/chat completion or NovelAI presetVersion 3 JSON · Up to 1 MiB. Select the instructions to keep as a recipe. Sampling changes need a separate local profile review. Files containing recognized credential fields are rejected before preservation.</p>
    <details><summary>Recent preset sources</summary><ErrorNotice message={history.error?.message} />{history.data?.map(item => <button className="text-button migration-history" key={item.id} onClick={() => setId(item.id)}>{item.filename} · {item.published_versions} published versions</button>)}</details>
    <ErrorNotice message={action.error || query.error?.message} />{(action.busy || (id && query.isPending)) && <Loading label="Preparing your preset review…" />}
    {!action.busy && query.data && <PresetReview key={query.data.id} preview={query.data} />}
  </div>
}
