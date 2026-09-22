import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useEffect, useRef, type RefObject } from 'react'
import { ArrowUp } from 'lucide-react'
import { readyProfiles } from '../models/profileReadiness'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch, Story } from '../../types'
import type { ProfileList } from '../models/types'
import type { SideSettings as Settings } from './sideSettings'
import { DraftRecovery } from '../textEdits/DraftRecovery'
import { useSideDraft } from './useSideDraft'
import { useSideRequests } from './useSideRequests'
import type { SavedRequest } from '../generation/requestRecovery'
import { useCompanionContext } from './useCompanionContext'
import type { ContextHead } from './contextTypes'
import { CompanionWorkControls } from './CompanionWorkControls'
import { workBody, workPresentation } from './workTypes'
import { useSidePreview } from './useSidePreview'
const SideRequestPreview = lazy(() => import('./SideRequestPreview'))
export type PrepareCompanion = RefObject<(() => Promise<void>) | null>

export function SideComposer({ threadId, branch, story, working, settings, onSettings, prepare: prepareRef }: { threadId: string; branch: Branch; story: Story; working: boolean; settings: Settings; onSettings: (settings: Settings) => void; prepare?: PrepareCompanion }) {
  const draft = useSideDraft(story.id, threadId)
  const requests = useSideRequests(threadId)
  const action = useAction()
  const context = useCompanionContext(threadId)
  const preview = useSidePreview(JSON.stringify([threadId, draft.text, settings, context.data?.revision, branch.id, branch.revision, story.revision]))
  const previewTrigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!prepareRef) return
    const flush = async () => { await draft.controller.flush() }
    prepareRef.current = flush
    return () => { if (prepareRef.current === flush) prepareRef.current = null }
  }, [draft.controller, prepareRef])
  const prepare = async () => {
    if (requests.pending.length || requests.error) throw new Error('Resolve the saved question request before sending another.')
    const saved = await draft.controller.flush()
    if (saved.text !== draft.text) throw new Error('The conversation draft changed. Review its current wording before asking.')
    if (!context.data) throw new Error('Wait for the saved Companion target before asking.')
    return { operation_id: operationId(),
      question: saved.text, expected_draft_version: saved.version, profile_ids: settings.profiles, disclosure: settings.disclosure, max_reads: settings.reads,
      ...questionScope(context.data, branch, settings.paths), ...workBody(settings.work) }
  }
  const ask = () => action.run(async () => {
    const body = await prepare()
    await requests.submit({ kind: 'side-question', path: `/side-conversations/${threadId}/questions`, body: { ...body, ...(preview.fingerprint ? { expected_preview: preview.fingerprint } : {}) } })
    await draft.controller.refresh()
  })
  const invalidComparison = settings.compare && settings.profiles.length < 2
  const locked = [action.busy, requests.pending.length > 0].some(Boolean)
  const presentation = workPresentation(settings.work, context.data)
  const unavailable = [!context.data, !!context.error, !!requests.error, presentation.unavailable].some(Boolean)
  const cannotSend = [!draft.text.trim(), draft.phase !== 'ready', working, locked, invalidComparison, unavailable].some(Boolean)
  return <form className="side-composer" onSubmit={(e) => { e.preventDefault(); void ask() }}><ErrorNotice message={action.error || requests.error} />
    <CompanionWorkControls storyId={story.id} value={settings.work} onChange={work => onSettings({ ...settings, work })} target={context.data?.context} locked={[locked, working].some(Boolean)} /><textarea aria-label="Message to collaborator" placeholder={presentation.placeholder} rows={3} maxLength={30000} disabled={[locked, draft.phase === 'loading'].some(Boolean)} value={draft.text} onChange={(e) => draft.controller.edit(e.target.value)} />
    <SideSubmit presentation={presentation} disabled={cannotSend} />
    <button ref={previewTrigger} type="button" className="text-button" disabled={cannotSend} onClick={() => void action.run(async () => preview.load(threadId, await prepare()))}>Preview Companion request</button>
    {preview.open && preview.value && <Suspense fallback={<p role="status">Opening preview…</p>}><SideRequestPreview value={preview.value} current={preview.current} onClose={preview.close} focusOnClose={() => previewTrigger.current} /></Suspense>}
    <DraftRecovery draft={draft} />
    <PendingQuestions requests={requests.pending} busy={action.busy} onRecover={request => void action.run(async () => { await requests.submit(request); await draft.controller.refresh() })} onCheck={() => void action.run(requests.refresh)} />
    <SideOptions branch={branch} story={story} settings={settings} onChange={onSettings} pinned={!!context.data?.context} />
  </form>
}

function PendingQuestions({ requests, busy, onRecover, onCheck }: { requests: SavedRequest[]; busy: boolean; onRecover: (request: SavedRequest) => void; onCheck: () => void }) {
  if (!requests.length) return null
  return <section className="request-recovery" aria-label="Saved question requests"><p>These questions have an unresolved delivery status. Reopening this view does not resend them.</p>{requests.map(request => <div key={request.body.operation_id}><pre>{String(request.body.question)}</pre><button type="button" className="button" disabled={busy} onClick={() => onRecover(request)}>Recover question request</button></div>)}<button type="button" className="text-button" disabled={busy} onClick={onCheck}>Check saved request status</button></section>
}

function questionScope(head: ContextHead, branch: Branch, paths: string[]) {
  const pin = head.context, selected = pin ? pin.branch : branch
  return { branch_id: selected.id, expected_revision: selected.revision, expected_context_revision: head.revision,
    compare_branch_ids: pin ? [] : paths, ...(pin ? { context_id: pin.id } : {}) }
}

const toggle = (items: string[], id: string) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]

function SideOptions({ branch, story, settings, onChange, pinned }: { branch: Branch; story: Story; settings: Settings; onChange: (settings: Settings) => void; pinned: boolean }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const patch = (next: Partial<Settings>) => onChange({ ...settings, ...next })
  return <details className="side-options"><summary>Model, sources & disclosure</summary><ErrorNotice message={profiles.error?.message} />
    <label className="field"><span>Request profile override</span><select aria-label="Collaborator request profile override" disabled={settings.compare} value={settings.profiles[0] ?? ''} onChange={(e) => patch({ profiles: e.target.value ? [e.target.value] : [] })}><option value="">Use connection shown above</option>{profiles.data?.profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label>
    <label className="check-row"><input type="checkbox" checked={settings.compare} onChange={(e) => patch({ compare: e.target.checked, profiles: [] })} />Compare replies from several profiles</label>
    {settings.compare && <div className="side-profile-choices">{profiles.data?.profiles.map((profile) => <label key={profile.profile_id} className="check-row"><input type="checkbox" checked={settings.profiles.includes(profile.profile_id)} onChange={() => patch({ profiles: toggle(settings.profiles, profile.profile_id) })} />{profile.display_name ?? profile.name}</label>)}<small>Choose 2–4 profiles. Select one reply for the following discussion.</small></div>}
    <label className="field"><span>Disclosure</span><select aria-label="Collaborator disclosure" value={settings.disclosure} onChange={(e) => patch({ disclosure: e.target.value })}><option value="spoiler-conscious">Spoiler-conscious presentation</option><option value="full-disclosure">Full disclosure, including hidden lore</option></select></label>
    {pinned ? <p className="subtle">The pinned target keeps its saved sources. Follow the workspace or select another comparison to change that scope.</p> : <details><summary>Include other paths explicitly</summary>{story.branches.filter((item) => item.id !== branch.id).map((item) => <label className="check-row" key={item.id}><input type="checkbox" checked={settings.paths.includes(item.id)} onChange={() => patch({ paths: toggle(settings.paths, item.id) })} />{item.name}</label>)}</details>}
    <label className="field"><span>Additional source-reading passes</span><input aria-label="Source-reading passes" type="number" min={0} max={4} value={settings.reads} onChange={(e) => patch({ reads: Number(e.target.value) })} /></label><p className="subtle">At most {settings.reads + 1} model requests per profile. Long story mode uses paged archive search and exact passage reads. Other stories use the complete source index. Private background is excluded from Long story discovery unless you choose full disclosure. Coverage appears beside each reply.</p>
  </details>
}

function SideSubmit({ presentation, disabled }: { presentation: ReturnType<typeof workPresentation>; disabled: boolean }) {
  return <div className="side-send"><span className="subtle">{presentation.caption}</span><button className={presentation.editing ? 'button primary' : 'send-button'} type="submit" aria-label={presentation.label} disabled={disabled}>{presentation.editing ? presentation.label : <ArrowUp size={18} />}</button></div>
}
