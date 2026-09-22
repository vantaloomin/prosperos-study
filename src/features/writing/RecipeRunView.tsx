import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { OutcomeSummary } from '../mechanics/OutcomeSummary'
import { TargetCard } from '../textEdits/EditPresentation'
import type { EditInitial } from '../textEdits/types'
import { RecipePending } from './RecipePending'
import { RecipeGuidanceCard, RecipeRequestPreview, RecipeSwitchPreview } from './RecipeRequestPreview'
import { stepLabels } from './recipeEditorTypes'
import { activeRecipeJob, recipeStatus, type RecipeJob, type RecipeRun, type RecipeStepPreview } from './recipeRunTypes'
import { useRecipeOperation } from './useRecipeOperation'

export function RecipeRunView({ id, onEdit }: { id: string; onEdit: (value: EditInitial) => void }) {
  const query = useQuery({ queryKey: ['recipe-run', id], queryFn: () => api<RecipeRun>(`/recipe-runs/${id}`),
    refetchInterval: current => current.state.data?.progress.status === 'running' ? 1000 : 2500, retry: false })
  const run = query.data
  return <div className="recipe-run form-stack"><ErrorNotice message={query.error?.message} />{query.error && <button className="button" onClick={() => void query.refetch()}>Reconnect to saved run</button>}{query.isPending && <Loading label="Opening the saved recipe run…" />}{run && <RecipeRunContent run={run} onEdit={onEdit} />}</div>
}

function RecipeRunContent({ run, onEdit }: { run: RecipeRun; onEdit: (value: EditInitial) => void }) {
  return <>
    <div className="recipe-run-status"><h3>{recipeStatus[run.progress.status]}</h3><small>{new Date(run.created_at).toLocaleString()} · {run.snapshot.branch.name} · step revision {run.revision}</small></div><TargetCard target={run.target} /><p>Action: {run.snapshot.action.replaceAll('-', ' ')} · saved range {run.snapshot.selection.start}–{run.snapshot.selection.end}</p><pre className="recipe-selection" tabIndex={0}>{run.snapshot.selection.text || '(insertion point)'}</pre><RecipeGuidanceCard value={run.snapshot.guidance} /><RecipeSwitchPreview value={run.snapshot.switches} />
    {run.chance && <details><summary>Recorded chance result</summary><div className="form-stack"><p>{run.chance.eligibility || 'Prepared once for this draft. Accepted Story state is unchanged.'}</p><OutcomeSummary title="Event" outcome={run.chance.event} /><OutcomeSummary title="Handling" outcome={run.chance.handling} /><details><summary>Exact chance receipt</summary><pre className="recipe-literal" tabIndex={0}>{JSON.stringify(run.chance, null, 2)}</pre></details></div></details>}
    <ol className="recipe-stages">{run.snapshot.plan.map((stage, index) => <li key={index}><h3>{stepLabels[stage.task]}</h3>{stage.skipped ? <p>Skipped: {stage.reason}</p> : <>{run.jobs.filter(job => job.stage === index).map(job => <RecipeJobCard key={job.id} job={job} />)}{!run.jobs.some(job => job.stage === index) && <p className="subtle">{run.progress.stage === index ? 'Ready to preview the actual inputs.' : 'Waiting for the preceding step.'}</p>}</>}</li>)}</ol>
    {run.progress.status === 'ready' && <RecipeNextStep key={run.revision} run={run} />}{run.progress.status === 'needs-attention' && <p role="status">An unfinished step needs your attention. Retry its original inputs explicitly to continue.</p>}
    {run.proposals.map(proposal => <section className="text-target-card form-stack" key={proposal.id}><h3>Text proposal · {proposal.status}</h3><p>{proposal.explanation}</p><pre className="recipe-literal" tabIndex={0}>{proposal.replacement}</pre><button className="button primary" data-recipe-proposal={proposal.id} onClick={() => onEdit(proposal.receipt ? { receiptId: proposal.receipt.id } : { proposalId: proposal.id })}>{proposal.receipt ? 'View applied change & Undo' : 'Review wording & apply'}</button></section>)}
    {run.progress.status === 'complete' && !run.proposal_id && <p>Review complete. The reports above do not change the selected text.</p>}<p className="subtle">Saved runs remain available in Story workflow → Recipes. Closing this view leaves recorded work intact and does not start another step.</p>
  </>
}

function RecipeNextStep({ run }: { run: RecipeRun }) {
  const [preview, setPreview] = useState<RecipeStepPreview | null>(null)
  const action = useAction()
  const operation = useRecipeOperation(`prospero:recipe-step:${run.id}:${run.revision}`)
  const prepare = () => action.run(async () => { setPreview(await api<RecipeStepPreview>(`/recipe-runs/${run.id}/preview-step`, {})) })
  if (operation.pending) return <RecipePending operation={operation} />
  const current = preview?.revision === run.revision && preview.stage === run.progress.stage
  return <section className="form-stack" aria-label="Next recipe step"><ErrorNotice message={action.error || operation.error} /><button className="button" disabled={action.busy} onClick={() => void prepare()}>Preview next recipe step</button>{current && <><h3>Ready to send {preview.request_count} request{preview.request_count === 1 ? '' : 's'}</h3>{preview.jobs.map(request => <RecipeRequestPreview key={request.step} request={request} />)}<button className="button primary" disabled={operation.busy} onClick={() => void operation.send(`/recipe-runs/${run.id}/steps`, { expected_revision: preview.revision, preview_hash: preview.preview_hash })}>Start this recipe step</button></>}</section>
}

function RecipeJobCard({ job }: { job: RecipeJob }) {
  const action = useAction()
  const [history, setHistory] = useState(false)
  const attempts = useQuery({ queryKey: ['recipe-attempts', job.id, job.attempt, job.status], queryFn: () => api<RecipeJob[]>(`/recipe-jobs/${job.id}/attempts`), enabled: history })
  const command = (name: 'stop' | 'retry') => action.run(async () => { await api(`/recipe-jobs/${job.id}/${name}`, { expected_attempt: job.attempt + (job.status === 'queued' ? 1 : 0) }) })
  return <article className="recipe-request form-stack"><div className="recipe-run-status"><h4>{job.step} · {job.snapshot.profile.name}</h4><span role="status">{job.status} · attempt {job.attempt}</span></div><ErrorNotice message={job.error || action.error} />
    {job.result && <RecipeResult result={job.result} />}
    <div className="recipe-step-actions">{activeRecipeJob(job.status) && <button className="button" disabled={action.busy} onClick={() => void command('stop')}>Stop this recipe request</button>}{['error', 'cancelled', 'interrupted'].includes(job.status) && <button className="button" disabled={action.busy} onClick={() => void command('retry')}>Retry original recipe inputs</button>}<button className="text-button" onClick={() => setHistory(!history)}>{history ? 'Hide' : 'Show'} recipe attempts</button></div>
    <details><summary>Original response & saved request</summary><pre className="recipe-literal" tabIndex={0}>{job.output || '(no output received)'}</pre><RecipeRequestPreview request={job.snapshot} /></details>{history && <><ErrorNotice message={attempts.error?.message} />{attempts.data?.map(attempt => <details key={attempt.id}><summary>Attempt {attempt.attempt} · {attempt.status}</summary><p>{attempt.error}</p><pre className="recipe-literal" tabIndex={0}>{attempt.output || '(no output)'}</pre></details>)}</>}
  </article>
}

function RecipeResult({ result }: { result: NonNullable<RecipeJob['result']> }) {
  if ('summary' in result) return <><p>{result.summary}</p>{result.findings.map((finding, index) => <blockquote key={index}><p><strong>{finding.severity}{finding.lens ? ` · ${finding.lens}` : ''}</strong> · {finding.explanation}</p><p>“{finding.quote}”</p><p>{finding.suggestion}</p><small>Source: {finding.source_id}</small></blockquote>)}{result.coverage && <details><summary>Beat coverage report</summary><pre className="recipe-literal">{JSON.stringify(result.coverage, null, 2)}</pre></details>}</>
  return <><pre className="recipe-literal" tabIndex={0}>{result.replacement}</pre><p>{result.explanation}</p><small>Sources: {result.source_ids.join(', ') || 'No cited sources'}</small></>
}
