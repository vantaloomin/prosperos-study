import type { ContextReport } from './contextTypes'
import { KnowledgeCoverage } from './KnowledgeChoice'

export function MemoryCoverage({ report }: { report: ContextReport }) {
  return report.knowledge_lens ? <KnowledgeCoverage report={report.knowledge_lens} /> : <StoryCoverage report={report} />
}

function StoryCoverage({ report }: { report: ContextReport }) {
  const { coverage, memory } = report
  const included = (coverage.included_messages ?? coverage.messages).toLocaleString()
  const total = coverage.messages.toLocaleString()
  const summarized = summaryCount(coverage.summarized_messages ?? 0)
  const headline = coverage.complete_path
    ? 'Complete selected path · ' + total + ' contributions'
    : included + ' of ' + total + ' complete contributions · ' + (coverage.recalled_passages ?? 0) + ' exact earlier excerpts' + summarized
  return <div className="context-coverage"><span>{headline}</span>
    <small>Branch revision {report.branch_revision} · Story revision {report.story_revision} · Writer prompt v{report.prompt_version}</small>
    {memory && <><p>Long story memory · originals remain available. {coverage.complete_path ? 'The whole path fits this request.' : 'Only the selected context reaches the model. Missing details are not evidence that something never happened.'}</p>
      <small>Compared writers receive the same context, sized to the smallest selected allowance. Recall makes no extra model calls.</small>
      <SummaryDetails report={report} /><PlanCoverage report={report} />
      {memory.canon && <details><summary>Canon recall coverage</summary><ul>{memory.canon.collections.map((item) => <li key={item.version_id}>{item.name} v{item.number}: {item.selected_chunks} of {item.chunks} overview excerpts{item.stale_cues > 0 ? ' · ' + item.stale_cues + ' outdated search cues excluded' : ''}</li>)}</ul><p className="subtle">Only enabled, pinned collection versions are searched. Native entry activation stays separate. Read exact text under Recalled Canon references.</p></details>}
      {!!memory.selected.length && <details><summary>Why earlier passages were recalled</summary><ul>{memory.selected.map((item) => <li key={item.id}>{item.reason}</li>)}</ul><p className="subtle">Read the exact excerpts and source references under Included sources.</p></details>}
    </>}
  </div>
}

function summaryCount(count: number) {
  if (!count) return ''
  return ' · ' + count + ' summarized ' + (count === 1 ? 'contribution' : 'contributions')
}

function SummaryDetails({ report }: { report: ContextReport }) {
  const aids = report.memory?.summary_aids ?? []
  return <>
{!!report.coverage.summarized_messages && <p>Reviewed summaries are interpretations of older prose and may leave details out. Read them, their exact grounding quotes, and source references under Reviewed summaries in context.</p>}
{!!aids.length && <details><summary>Reviewed summaries used for recall ({aids.length})</summary><p className="subtle">These aids helped index the selected originals. These recall receipts correspond to exact excerpts. Any summaries supplied as context are labeled separately.</p><ul>{aids.map(aid => <li key={aid.chunk_id}>{aid.summary}<small className="subtle">Memory version {aid.version_id}</small></li>)}</ul></details>}
  </>
}

function PlanCoverage({ report }: { report: ContextReport }) {
  const plans = report.memory?.plans
  if (!plans) return null
  return <p>{plans.selected_ids.length} of {plans.available} recorded plans included. {plans.omitted_ids.length > 0
    ? 'Other plans did not fit their context allowance; they remain in Story memory. An indirect reference may still be ambiguous.'
    : 'Their current states and source excerpts are supplied without replaying every earlier correction.'}</p>
}
