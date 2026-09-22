import type { BeatCoverage, DraftBlock, SceneJob, SceneResult, SceneRun } from './types'
import { SceneDraftEdits } from '../textEdits/SceneDraftEdits'

export function DraftBlocks({ blocks }: { blocks: DraftBlock[] }) {
  return <div className="scene-prose">{blocks.map((block) => <div key={block.id}>
    {block.text != null ? block.text.split('\n\n').map((paragraph, index) => <p className="prose" key={index}>{paragraph || '(empty block)'}</p>) : block.kind === 'dialogue' && <aside className="scene-dialogue-slot"><strong>Spoken line · {block.speaker}</strong><p>{block.instruction}</p><small>Waiting for the dialogue writer</small></aside>}
  </div>)}</div>
}

function ProposedFacts({ facts }: { facts: string[] }) {
  if (!facts.length) return null
  return <section className="scene-proposed-facts"><h4>New details proposed by the writer</h4><p className="subtle">These have not been added to canon. Later continuity review must decide what to keep.</p><ul>{facts.map((fact, index) => <li key={index}>{fact}</li>)}</ul></section>
}

export function DraftStageArtifact({ job, run }: { job: SceneJob; run: SceneRun }) {
  const result = job.result!
  if (result.blocks) return <div className="form-stack"><p className="scene-summary">{result.summary}</p><DraftBlocks blocks={result.blocks} /><ProposedFacts facts={result.proposed_facts ?? []} /></div>
  if (result.lines) return <DialogueArtifact job={job} result={result} />
  return <CoverageArtifact result={result} run={run} />
}

function DialogueArtifact({ job, result }: { job: SceneJob; result: SceneResult }) {
  const skeleton = (JSON.parse(job.snapshot.content) as { skeleton: { blocks: DraftBlock[] } }).skeleton
  const speakers = new Map(skeleton.blocks.filter((block) => block.kind === 'dialogue').map((block) => [block.id, block.speaker]))
  return <div className="form-stack"><p className="scene-summary">{result.summary}</p>{result.lines!.map((line) => <article key={line.slot_id} className="scene-spoken-line"><h4>{speakers.get(line.slot_id)}</h4><p className="prose">{line.text}</p></article>)}<p className="subtle">Selecting these lines fills the saved slots. Narration remains as drafted.</p></div>
}

function CoverageArtifact({ result, run }: { result: SceneResult; run: SceneRun }) {
  const beats = result.beats as BeatCoverage[]
  const issues = result.issues ?? []
  const passed = !issues.length && beats.every((beat) => beat.status === 'rendered')
  return <div className="form-stack"><div className="scene-notice"><strong>{passed ? 'Every beat is accounted for' : 'This draft needs another pass'}</strong><p>{result.summary}</p><small>This is a coverage assessment, not approval to add Story text.</small></div>{beats.map((beat) => <article className="review-finding" key={beat.beat_id}><h4>{run.plan?.beats.find((item) => item.id === beat.beat_id)?.title ?? beat.beat_id} · {beat.status}</h4>{beat.quotes.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}<p>{beat.explanation}</p></article>)}{issues.map((issue, index) => <article className="review-finding" key={index}><h4>{issue.category}</h4><blockquote>{issue.quote}</blockquote><p>{issue.explanation}</p></article>)}</div>
}

export function SelectedDraft({ run, onRedraft, onBranch }: { run: SceneRun; onRedraft: () => void; onBranch: (id: string) => void }) {
  const draft = run.draft!
  const reviewed = !!run.state.selections['scene-coverage'] && !run.state.accepted
  return <section className="scene-selected-draft form-stack"><details><summary>{draft.complete ? 'Read the selected scene draft' : 'Read the selected skeleton · dialogue pending'}</summary><DraftBlocks blocks={draft.blocks} /><ProposedFacts facts={draft.proposed_facts} /></details>
    <SceneDraftEdits run={run} onBranch={onBranch} />
    {reviewed && <div className="scene-notice"><p>{run.coverage_passes ? 'Coverage is complete. This saved draft still needs independent review, revision decisions and explicit Story acceptance.' : 'The selected assessment found incomplete beats or other issues. A new draft request includes this assessment; choosing a replacement clears dependent selections.'}</p>{!run.coverage_passes && <button className="button" disabled={run.stale} onClick={onRedraft}>Return to drafting</button>}</div>}
  </section>
}
