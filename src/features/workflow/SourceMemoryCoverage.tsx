export interface SourceMemoryReceipt {
  mode: 'long'
  canon?: { coverage: { collections: number; available_excerpts: number; selected_excerpts: number } }
  selective: boolean
  selection?: { reviewed_aid?: { version_id: string } }[]
  coverage: { history_sources: number; included_history: number; recalled_passages: number; summarized_passages?: number; complete_history: boolean }
}

export function SourceMemoryCoverage({ memory }: { memory?: SourceMemoryReceipt | null }) {
  if (!memory) return null
  const coverage = memory.coverage
  return <p className="subtle">{coverage.complete_history
    ? 'Long Story Memory · all earlier contributions supplied to this step fit.'
    : `Long Story Memory · ${coverage.included_history} of ${coverage.history_sources} earlier contributions in full, plus ${coverage.recalled_passages} exact excerpts.`}
    <SummaryCoverage count={coverage.summarized_passages ?? 0} />
    {!coverage.summarized_passages && memory.selection?.some(item => item.reviewed_aid) && ' Reviewed memory helped locate original prose; derived summaries are not supplied as facts.'}
    <CanonCoverage coverage={memory.canon?.coverage} />
    {' '}Working material, guidance, Character definitions and required references stay intact. Missing context is not evidence of a contradiction.
  </p>
}

function CanonCoverage({ coverage }: { coverage?: NonNullable<SourceMemoryReceipt['canon']>['coverage'] }) {
  if (!coverage) return null
  const excerpts = coverage.selected_excerpts === 1 ? 'excerpt' : 'excerpts'
  const collections = coverage.collections === 1 ? 'collection' : 'collections'
  return <>{` Canon · ${coverage.selected_excerpts} exact ${excerpts} from ${coverage.collections} ${collections} set to Relevant excerpts.`}
    {coverage.selected_excerpts < coverage.available_excerpts ? ' Other overview details are omitted.' : ' These excerpts cover the complete overview text.'}
  </>
}

export function SourceMemoryDetails({ memory }: { memory?: SourceMemoryReceipt }) {
  if (!memory) return null
  return <><h4>Memory receipt</h4><pre>{JSON.stringify(memory, null, 2)}</pre></>
}

function SummaryCoverage({ count }: { count: number }) {
  if (!count) return null
  return <>{` ${count} reviewed ${count === 1 ? 'summary' : 'summaries'} supplied with exact grounding quotes. These interpretations can omit details.`}</>
}
