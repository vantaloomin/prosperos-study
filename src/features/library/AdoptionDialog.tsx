import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { AdoptionPreview, AssetVersion } from '../../types'
import { AdoptionTargets, RelatedUpdates } from './AdoptionTargets'

export function AdoptionDialog({ version, onClose, focusOnClose }: { version: AssetVersion; onClose: () => void; focusOnClose?: () => HTMLElement | null }) {
  const [related, setRelated] = useState<string[]>([])
  const query = useQuery({ queryKey: ['adoption', version.id, related], queryFn: () => api<AdoptionPreview>(`/versions/${version.id}/adoption/preview`, { additional_version_ids: related }), staleTime: 0 })
  const action = useAction()
  const [focusVersion, setFocusVersion] = useState<string | null>(null)
  const operation = useRef({ hash: '', id: '' })
  const apply = () => action.run(async () => {
    const preview = query.data
    if (!preview || !preview.can_apply) return
    if (operation.current.hash !== preview.preview_hash) operation.current = { hash: preview.preview_hash, id: operationId() }
    await api(`/versions/${version.id}/adoption`, { operation_id: operation.current.id, additional_version_ids: related,
      preview_hash: preview.preview_hash, targets: preview.targets.map(({ story_id, expected_revision, manifest_id }) => ({ story_id, expected_revision, manifest_id })) })
    onClose()
  })
  const changeRelated = (ids: string[]) => {
    setFocusVersion(ids.find((id) => !related.includes(id)) ?? ids.at(-1) ?? '')
    setRelated(ids)
  }
  const include = (id: string) => { if (!related.includes(id)) changeRelated([...related, id]) }
  return <Modal open wide onClose={onClose} focusOnClose={focusOnClose} title={`Use ${version.name} v${version.number}`} description="Review changes to future guidance. Existing messages, continuity, runs and earlier versions stay preserved.">
    <div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />
      {query.isPending ? <Loading label="Checking Story versions and linked lore…" /> : <AdoptionTargets preview={query.data} busy={action.busy} onInclude={include} />}
      {query.data && <RelatedUpdates preview={query.data} related={related} onChange={changeRelated} busy={action.busy} focusVersion={focusVersion} />}
      <p className="subtle">All existing Stories using any selected item are included, even archived Stories. Removed character links leave already-attached Canon collections in place. Textual contradictions with accepted canon still need your review.</p>
      <ErrorNotice message={action.error} /><button className="text-button" disabled={action.busy || query.isFetching} onClick={() => { action.clearError(); void query.refetch() }}>Refresh affected stories</button>
    </div><AdoptionFooter preview={query.data} busy={action.busy} refreshing={query.isFetching} error={!!query.error} onClose={onClose} onApply={apply} />
  </Modal>
}

function adoptionState(preview?: AdoptionPreview) {
  const changed = preview?.targets.filter((target) => target.changed).length ?? 0
  return { changed, allowed: !!preview?.can_apply && changed > 0 }
}

function AdoptionFooter({ preview, busy, refreshing, error, onClose, onApply }: { preview?: AdoptionPreview; busy: boolean; refreshing: boolean; error: boolean; onClose: () => void; onApply: () => void }) {
  const state = adoptionState(preview)
  return <footer className="dialog-footer"><button className="button" onClick={onClose}>Keep existing versions</button><button className="button primary" disabled={busy || refreshing || error || !state.allowed} onClick={onApply}>{busy ? 'Updating…' : `Update all ${state.changed} ${state.changed === 1 ? 'Story' : 'Stories'}`}</button></footer>
}
