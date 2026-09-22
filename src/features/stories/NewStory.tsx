import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Feather } from 'lucide-react'
import { readyProfiles } from '../models/profileReadiness'
import { api, ApiError, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { AssetVersion, Selection } from '../../types'
import type { ProfileList } from '../models/types'
import { experienceChange, openingSourceAttached, selectedAssets, setupSteps, storyStart, type SetupDraft } from './setup'
import { useSetupDraft } from './useSetupDraft'
import { ExperienceChoice } from './WritingPreferences'
import { SetupWriter } from './SetupWriter'
import { SetupPeople } from './SetupPeople'
import { SetupAssistance, SetupReview, SetupStory } from './SetupContent'
import '../../styles/onboarding.css'

const ArchiveImport = lazy(() => import('../export/Archives').then((module) => ({ default: module.ArchiveImport })))
const noProfiles: ProfileList = { profiles: [], primary_profile_id: null }
interface Props { onClose: () => void; onCreated: (selection: Selection) => void }

export function NewStory({ onClose, onCreated }: Props) {
  const { draft, patch, reset, storageError } = useSetupDraft()
  const library = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const action = useAction()
  const finish = (selection: Selection) => { reset(); onCreated(selection); onClose() }
  const submit = (skip = false) => action.run(async () => {
    const payload = draft.pending ?? storyStart(draft, profiles.data ?? noProfiles, library.data ?? [], operationId(), skip)
    patch({ pending: payload, title: payload.title, step: 5 })
    try {
      const result = await api<{ story_id: string; branch_id: string }>('/stories', payload)
      finish({ storyId: result.story_id, branchId: result.branch_id })
    } catch (error) {
      if (error instanceof ApiError && [400, 404, 422].includes(error.status)) patch({ pending: null })
      if (!(error instanceof ApiError)) throw new Error('The local app could not confirm this save. Reconnect, then retry your saved setup.')
      throw error
    }
  })
  const changeStep = (step: number) => {
    action.clearError()
    patch({ step, furthestStep: Math.max(step, draft.furthestStep), assets: selectedAssets(draft, library.data ?? []), legacyAssets: unresolvedLegacy(draft, library.data ?? []) })
  }
  const referenceError = referenceFailure(library.error, profiles.error)
  const loaded = !!library.data && !!profiles.data
  return <Modal open onClose={onClose} title="Make room for a story" description="Start with a spark. Close any time; your unfinished setup stays on this device.">
    <SetupProgress step={draft.step} furthest={draft.furthestStep} locked={action.busy || !!draft.pending} onStep={changeStep} />
    <div className="dialog-body setup-body"><StepHeading step={draft.step} /><ErrorNotice message={storageError} /><ErrorNotice message={referenceError} />{referenceError && <button className="button" onClick={() => { void library.refetch(); void profiles.refetch() }}>Retry loading choices</button>}
      {draft.pending && <p className="setup-callout" role="status">This setup has been submitted. Retry the same save to recover its result without creating a duplicate Story. Your submitted choices are preserved.</p>}
      <SetupStep draft={draft} patch={patch} library={library.data ?? []} profiles={profiles.data ?? noProfiles} onStep={changeStep} onImported={finish} />
      {!loaded && <Loading label="Loading saved choices…" />}
    </div>
    {action.error && <div className="setup-save-error"><ErrorNotice message={action.error} /></div>}
    <SetupFooter draft={draft} busy={action.busy} loaded={loaded} onStep={changeStep} onSubmit={() => void submit()} onSkip={() => void submit(true)} />
  </Modal>
}

function referenceFailure(library: Error | null, profiles: Error | null) {
  return library?.message || profiles?.message
}

function unresolvedLegacy(draft: SetupDraft, library: AssetVersion[]) {
  return draft.legacyAssets.filter((id) => !library.some((asset) => asset.asset_id === id))
}

function SetupProgress({ step, furthest, locked, onStep }: { step: number; furthest: number; locked: boolean; onStep: (step: number) => void }) {
  return <nav className="setup-progress" aria-label="Story setup steps">{setupSteps.map((name, index) => <button key={name} disabled={locked || index > furthest} aria-current={step === index ? 'step' : undefined} onClick={() => onStep(index)}><span>{index + 1}</span><small>{name}</small></button>)}</nav>
}

function StepHeading({ step }: { step: number }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: 'start' }) }, [step])
  return <h3 ref={heading} tabIndex={-1} className="setup-step-heading"><span className="eyebrow">STEP {step + 1} OF 6</span>{['Choose your way in', 'Find your writing partner', 'The first spark', 'People & world', 'Set the pace', 'Ready when you are'][step]}</h3>
}

interface StepProps { draft: SetupDraft; patch: (next: Partial<SetupDraft>) => void; library: AssetVersion[]; profiles: ProfileList; onStep: (step: number) => void; onImported: (selection: Selection) => void }
function SetupStep({ draft, patch, library, profiles, onStep, onImported }: StepProps) {
  if (draft.step === 0) return <SetupExperience draft={draft} patch={patch} onImported={onImported} />
  if (draft.step === 1) return <SetupWriter value={draft.primary_profile_id} profiles={profiles} onChange={(primary_profile_id) => patch({ primary_profile_id })} />
  if (draft.step === 2) return <SetupStory draft={draft} patch={patch} />
  if (draft.step === 3) return <SetupPeople draft={draft} patch={patch} library={library} />
  if (draft.step === 4) return <SetupAssistance draft={draft} patch={patch} />
  return <SetupReview draft={draft} profiles={profiles} onEdit={onStep} />
}

function SetupExperience({ draft, patch, onImported }: Pick<StepProps, 'draft' | 'patch' | 'onImported'>) {
  const [importing, setImporting] = useState(false)
  return <div className="form-stack"><ExperienceChoice value={draft.experience} onChange={(experience) => patch(experienceChange(experience))} /><p className="subtle">This guides your writing partner; all writing and review tools remain available.</p><button className="text-button" onClick={() => setImporting(true)}>Start from a private Story archive</button>{importing && <Modal open title="Bring a Story back" description="Review a saved archive before restoring it as a new Story." onClose={() => setImporting(false)}><div className="dialog-body"><Suspense fallback={<Loading label="Opening import…" />}><ArchiveImport onOpen={onImported} /></Suspense></div></Modal>}</div>
}

function SetupFooter({ draft, busy, loaded, onStep, onSubmit, onSkip }: { draft: SetupDraft; busy: boolean; loaded: boolean; onStep: (step: number) => void; onSubmit: () => void; onSkip: () => void }) {
  const final = draft.step === setupSteps.length - 1
  const blocked = nextBlocked(draft, loaded)
  const canSkip = !final && !draft.pending
  return <footer className="dialog-footer setup-footer">
    {canSkip && <p className="subtle setup-skip-hint" id="skip-setup-description">Start now. You can change these settings later.</p>}
    <button className="text-button" disabled={draft.step === 0 || busy || !!draft.pending} onClick={() => onStep(draft.step - 1)}><ArrowLeft size={16} />Back</button>
    <div className="setup-footer-actions">{canSkip && <button className="button" disabled={busy || !loaded} aria-describedby="skip-setup-description" onClick={onSkip}>Skip setup</button>}
      <button className="button primary" disabled={busy || blocked} onClick={final ? onSubmit : () => onStep(draft.step + 1)}>{nextLabel(draft, busy)}{final ? <Feather size={16} /> : <ArrowRight size={16} />}</button>
    </div>
  </footer>
}

function nextBlocked(draft: SetupDraft, loaded: boolean) {
  if (draft.pending) return false
  if (draft.step === 3) return !openingSourceAttached(draft.opening_source, draft.assets)
  if (draft.step === 2 || draft.step === 5) return !draft.title.trim() || !loaded
  return false
}

function nextLabel(draft: SetupDraft, busy: boolean) {
  if (busy) return 'Saving your Story…'
  if (draft.pending) return 'Retry saved setup'
  return draft.step === setupSteps.length - 1 ? 'Start writing' : 'Continue'
}
