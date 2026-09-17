import { DraftStageArtifact } from './DraftArtifacts'
import { RevisionArtifact } from './RevisionArtifact'
import { PatchArtifact } from './PatchArtifacts'
import { ContinuityArtifact } from './ContinuityWorkspace'
import { planningStep, type BeatPlan, type SceneJob, type SceneRun, type SceneResult } from './types'

export function BeatView({ plan }: { plan: BeatPlan }) {
  return <div className="form-stack"><p className="scene-summary">{plan.summary}</p><ol className="scene-beats">{plan.beats.map((beat) => <li key={beat.id}><h4>{beat.title}</h4><p>{beat.development}</p><p><strong>Open decision:</strong> {beat.decision}</p><p className="subtle"><strong>Preserve:</strong> {beat.constraints}</p></li>)}</ol><p><strong>Stopping point:</strong> {plan.ending}</p></div>
}

export function SceneArtifact({ job, run, disabled, onChoose }: { job: SceneJob; run: SceneRun; disabled: boolean; onChoose: (option?: string) => void }) {
  const result = job.result
  if (!result) return null
  if (job.step === 'scene-continuity') return <ContinuityArtifact result={result} />
  if (result.edits || result.checks) return <PatchArtifact result={result} />
  if (job.step === 'scene-triage' || job.step === 'scene-verify') return <RevisionArtifact result={result} />
  if (!planningStep(job.step)) return <DraftStageArtifact job={job} run={run} />
  return <PlanningArtifact job={job} result={result} run={run} disabled={disabled} onChoose={onChoose} />
}

function PlanningArtifact({ job, result, run, disabled, onChoose }: { job: SceneJob; result: SceneResult; run: SceneRun; disabled: boolean; onChoose: (option?: string) => void }) {
  if (result.options) return <div className="form-stack"><p className="scene-summary">{result.summary}</p><div className="scene-options">{result.options.map((option) => {
    const chosen = run.state.selections[job.step] === job.id && run.state.option_id === option.id
    return <article className="scene-option form-stack" key={option.id} data-chosen={chosen}><h4>{option.id} · {option.title}</h4><p>{option.direction}</p><p className="subtle"><strong>Opens:</strong> {option.opens}</p><p className="subtle"><strong>Closes:</strong> {option.closes}</p><button className="button" disabled={disabled || chosen} onClick={() => onChoose(option.id)}>{chosen ? `Option ${option.id} selected` : `Choose option ${option.id}`}</button></article>
  })}</div></div>
  if (result.beats) return <BeatView plan={result as BeatPlan} />
  return <div className="form-stack"><p className="scene-summary">{result.summary}</p>{result.facts?.map((fact, index) => <article className="review-finding" key={index}><blockquote>{fact.quote}</blockquote><p>{fact.relevance}</p><small>Source: {fact.source_id}</small></article>)}{!result.facts?.length && <p className="subtle">No established facts were cited.</p>}{!!result.unknowns?.length && <div><h4>Still unresolved</h4><ul>{result.unknowns.map((unknown, index) => <li key={index}>{unknown}</li>)}</ul></div>}</div>
}
