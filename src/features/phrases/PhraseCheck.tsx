import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch } from '../../types'
import { PhraseFindings } from './PhraseFindings'
import { rememberChoice } from './preferences'
import { usePhrasePreferences } from './usePhrasePreferences'
import type { PhrasePreferences, PhraseReport, PhraseScope } from './types'
import './phrase-check.css'

interface Props { branch: Branch; onClose: () => void; onRead: (id: string) => void; focusOnClose: () => HTMLElement | null }
interface Scan { expected_revision: number; scope: PhraseScope; minimum: number; attempt: number }

export default function PhraseCheck({ branch, onClose, onRead, focusOnClose }: Props) {
  const preferences = usePhrasePreferences(branch.id)
  const [scope, setScope] = useState<PhraseScope>('recent')
  const [minimum, setMinimum] = useState(3)
  const [scan, setScan] = useState<Scan | null>(null)
  const enabled = preferences.value.enabled && !preferences.unreadable
  const query = useQuery({ queryKey: ['phrase-check', branch.id, scan], enabled: enabled && !!scan,
    queryFn: () => api<PhraseReport>(`/branches/${branch.id}/phrase-check`, { expected_revision: scan!.expected_revision, scope: scan!.scope, minimum: scan!.minimum }),
    staleTime: Infinity, gcTime: 0, retry: false, refetchOnWindowFocus: false, refetchOnMount: false })
  const stale = reportIsStale(query.data, branch.revision, scope, minimum)
  const toggle = (value: boolean) => { preferences.update(current => ({ ...current, enabled: value })); setScan(null) }
  return <Modal open wide title="Phrase check" description="Notice repeated wording, compare its context, and decide what belongs in your story." onClose={onClose} focusOnClose={focusOnClose}>
    <div className="dialog-body form-stack phrase-check"><label className="check-row"><input type="checkbox" checked={enabled} disabled={preferences.unreadable} onChange={event => toggle(event.target.checked)} />Enable phrase checks on this path</label>
      <p className="subtle">Checks run locally when you ask. Repetition is an observation; your voice and intentional echoes belong to you.</p>
      <PreferenceProblem preferences={preferences} onReset={() => { preferences.reset(); setScan(null) }} />
      {enabled ? <><div className="phrase-options"><label className="field"><span>Passages to check</span><select value={scope} onChange={event => setScope(event.target.value as PhraseScope)}>
        <option value="recent">Latest 20 prose passages</option><option value="extended">Latest 100 prose passages</option><option value="path">This path (within size limit)</option></select></label>
        <label className="field"><span>Minimum occurrences</span><select value={minimum} onChange={event => setMinimum(Number(event.target.value))}>{[2, 3, 4].map(count => <option key={count} value={count}>{count} or more</option>)}</select></label></div>
        <button className="button primary" disabled={query.isFetching} onClick={() => setScan({ expected_revision: branch.revision, scope, minimum, attempt: (scan?.attempt ?? 0) + 1 })}>{query.isFetching ? 'Checking wording…' : 'Check wording'}</button>
        <p className="subtle">Accepted prose only. Author’s notes, removed passages, and unaccepted drafts are excluded. Each check covers up to 200,000 characters or 40,000 words, keeping complete passages.</p>
        <ScanProblem error={query.error} branchId={branch.id} onReset={() => setScan(null)} />{query.isFetching && <Loading label="Comparing phrases on this path…" />}
        {stale && <p className="notice" role="status">The path or check settings changed. Check wording again before acting on these observations.</p>}
        {query.data && <PhraseFindings report={query.data} preferences={preferences.value} stale={stale} onChoice={(finding, kind) => preferences.update(current => rememberChoice(current, finding, kind))} onRead={onRead} />}
        <SavedChoices preferences={preferences.value} onChange={preferences.update} />
      </> : <p role="status">Phrase check is off. Enable it here whenever you want to review repeated wording.</p>}
      <p className="subtle">The toggle and hidden observations are saved on this device for this path. New branches start with their own choices. These review preferences never change writer instructions and are not included in story archives.</p>
    </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Back to writing</button></footer>
  </Modal>
}

function PreferenceProblem({ preferences, onReset }: { preferences: ReturnType<typeof usePhrasePreferences>; onReset: () => void }) {
  if (!preferences.error) return null
  return <><ErrorNotice message={preferences.error} /><div className="import-downloads"><button className="button" onClick={preferences.reload}>Reload local choices</button><button className="button" onClick={onReset}>Reset local phrase-check choices</button></div></>
}

function ScanProblem({ error, branchId, onReset }: { error: Error | null; branchId: string; onReset: () => void }) {
  const cache = useQueryClient()
  if (!error) return null
  return <><ErrorNotice message={error.message} /><button className="button" onClick={() => { onReset(); void cache.invalidateQueries({ queryKey: ['branch', branchId] }) }}>Refresh path</button></>
}

function reportIsStale(report: PhraseReport | undefined, revision: number, scope: PhraseScope, minimum: number) {
  return !!report && (report.revision !== revision || report.scope !== scope || report.minimum !== minimum)
}

function SavedChoices({ preferences, onChange }: { preferences: PhrasePreferences; onChange: (change: (value: PhrasePreferences) => PhrasePreferences) => void }) {
  const count = preferences.dismissed.length + preferences.intentional.length
  if (!count) return null
  return <details><summary>Hidden observations & intentional phrases ({count})</summary><div className="form-stack phrase-choices">
    <p className="subtle">Dismiss hides this exact group of occurrences; a new occurrence may appear again. Intentional hides this wording for future checks on this path. Restore a choice to see it again.</p>
    {(['dismissed', 'intentional'] as const).map(kind => preferences[kind].map(choice => <div className="phrase-choice" key={`${kind}:${choice.id}`}><span>“{choice.phrase}” <small>· {kind === 'intentional' ? 'intentional wording' : 'dismissed observation'}</small></span><button className="text-button" onClick={() => onChange(current => ({ ...current, [kind]: current[kind].filter(item => item.id !== choice.id) }))}>Restore</button></div>))}
  </div></details>
}
