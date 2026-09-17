import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { usePersistent } from '../../hooks/usePersistent'
import type { ModelProfile } from '../models/types'
import type { Routing } from '../workflow/types'
import type { SceneRun } from './types'
import type { AvailableReport } from './revisionTypes'
import { RevisionJobs } from './RevisionJobs'
import { RevisionDecisions } from './RevisionDecisions'

type Props = { run: SceneRun; profiles: ModelProfile[]; routing: Routing }

export function RevisionWorkspace(props: Props) {
  const [open, setOpen] = useState(!!props.run.revision_plan)
  if (props.run.snapshot.disabled_steps?.includes('scene-triage')) return null
  return <section className="scene-reviews form-stack"><div><h3>Decide what changes</h3><p className="subtle">Bring selected reports into triage, settle disputed claims, then choose a revision package. The Story stays unchanged.</p></div>
    <button className="button" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Close revision workspace' : 'Resolve reviews & choose changes'}</button>
    {open && <RevisionContent {...props} />}
  </section>
}

function RevisionContent(props: Props) {
  const { run, profiles } = props
  return <div className="form-stack"><details className="advanced-settings" open={!run.revision_plan}><summary>Prepare or compare triage</summary><TriageSetup {...props} /></details>
    {run.revision_plan && <RevisionDecisions run={run} plan={run.revision_plan} profiles={profiles} />}
  </div>
}

function TriageSetup({ run, profiles, routing }: Props) {
  const reports = useQuery({ queryKey: ['scene-reports', run.id], queryFn: () => api<AvailableReport[]>(`/scenes/${run.id}/reports`) })
  const [choices, setChoices] = usePersistent<Record<string, string>>(`roleplay:triage-reports:${run.id}`, {})
  const available = reports.data ?? []
  const ids = Object.values(choices).filter((id) => available.some((report) => report.id === id))
  const roles = routing.steps.filter((step) => available.some((report) => report.step === step.key))
  return <div className="form-stack"><p className="subtle">Choose one completed report per role. Preferred comparisons are labeled; nothing is selected automatically. Reports must refer to this exact draft and plan.</p>
    <ErrorNotice message={reports.error?.message} />{reports.isPending && <Loading label="Finding eligible reports…" />}
    {roles.map((role) => <label className="field" key={role.key}><span>Report for {role.name}</span><select value={ids.includes(choices[role.key]) ? choices[role.key] : ''} onChange={(event) => setChoices({ ...choices, [role.key]: event.target.value })}><option value="">Do not include this role</option>{available.filter((report) => report.step === role.key).map((report) => <option key={report.id} value={report.id}>{report.profile_name} · {report.findings} findings{report.preferred ? ' · preferred' : ''} · {new Date(report.created_at).toLocaleString()}</option>)}</select></label>)}
    {!reports.isPending && !available.length && <p className="subtle">Complete independent reviews of the current covered draft first.</p>}
    <RevisionJobs run={run} profiles={profiles} step="scene-triage" targets={{ review_job_ids: ids }} ready={!!ids.length && (run.coverage_passes || !!run.snapshot.disabled_steps?.includes('scene-coverage'))} />
  </div>
}
