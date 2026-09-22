import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { ComparedPassage, Comparison, ComparisonSource, DifferenceStatus, OpenPassage } from './types'
import { SendToCompanionButton } from '../collaborator/SendToCompanion'
import { selectedInline } from '../collaborator/selectedText'

const labels: Record<DifferenceStatus, string> = { unchanged: 'Unchanged', changed: 'Changed', added: 'Added in second telling', removed: 'Absent in second telling', omitted: 'Omitted in second telling', restored: 'Restored in second telling' }

function differenceNavigation(data: Comparison | undefined, offset: number) {
  const firstVisible = data?.rows[0]?.index ?? offset
  return { firstVisible, nextDifference: data?.difference_indices.find(index => index > firstVisible), priorDifference: data?.difference_indices.filter(index => index < firstVisible).at(-1) }
}

export function ComparisonReader({ id, onOpen, onSelect }: { id: string; onOpen: OpenPassage; onSelect: (id: string) => void }) {
  const [offset, setOffset] = useState(0)
  const [previous, setPrevious] = useState<number[]>([])
  const [onlyChanges, setOnlyChanges] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const query = useQuery({ queryKey: ['branch-comparison', id, offset, onlyChanges], queryFn: () => api<Comparison>(`/branch-comparisons/${id}?offset=${offset}&limit=8&differences_only=${onlyChanges}`) })
  const data = query.data
  const go = (next: number) => { setPrevious([...previous, offset]); setOffset(next); heading.current?.focus({ preventScroll: false }) }
  const back = () => { setOffset(previous.at(-1) ?? 0); setPrevious(previous.slice(0, -1)); heading.current?.focus({ preventScroll: false }) }
  const { firstVisible, nextDifference, priorDifference } = differenceNavigation(data, offset)
  return <section className="comparison-reader form-stack" aria-label="Telling comparison"><h3 ref={heading} tabIndex={-1}>The two tellings</h3><ErrorNotice message={query.error?.message} />{query.error && <button className="button" onClick={() => void query.refetch()}>Try comparison again</button>}{query.isPending && <Loading label="Comparing passages…" />}{data && <>
    <SendToCompanionButton label="Send comparison to Companion" prepare={() => ({ storyId: data.story_id, source: { kind: 'comparison', comparison_id: data.id }, label: `${data.left.name} · r${data.left.revision} compared with ${data.right.name} · r${data.right.revision}` })} /><div className="comparison-headings">{(['left', 'right'] as const).map(side => <div key={side}><span className="eyebrow">{side === 'left' ? 'First telling' : 'Second telling'}</span><h4>{data[side].name}</h4><p className="subtle">Saved revision {data[side].revision}{data[side].curation.archived ? ' · archived' : ''}</p><button className="text-button" onClick={() => onSelect(data[side].branch_id)}>Open this telling</button></div>)}</div>
    <p className="subtle">{data.shared_prefix_count} passages share the same beginning. {data.shared_source_count} passages have shared source ancestry, including later edits or omissions.</p><div className="comparison-counts" aria-label="Comparison totals">{Object.entries(data.counts).map(([status, count]) => <span key={status}>{labels[status as DifferenceStatus]}: {count}</span>)}</div>
    <div className="branch-tool-actions"><label className="check-row"><input type="checkbox" checked={onlyChanges} onChange={event => { setOnlyChanges(event.target.checked); setOffset(0); setPrevious([]) }} />Differences only</label><button className="button" disabled={priorDifference === undefined} onClick={() => priorDifference !== undefined && go(priorDifference)}>Previous difference</button><button className="button" disabled={nextDifference === undefined} onClick={() => nextDifference !== undefined && go(nextDifference)}>Next difference</button></div>
    <div className="comparison-passages">{data.rows.map(row => <article key={row.index} className="comparison-row" data-comparison-index={row.index}><h4>{row.index + 1} · {labels[row.status]}</h4><div className="comparison-columns"><Passage storyId={data.story_id} comparisonId={data.id} sourceSide="left" source={data.left} passage={row.left} side="First telling" onOpen={onOpen} /><Passage storyId={data.story_id} comparisonId={data.id} sourceSide="right" source={data.right} passage={row.right} side="Second telling" onOpen={onOpen} /></div>{row.diff_mode === 'common-edges' && <p className="subtle">Long passages highlight the changed middle between their shared beginning and ending.</p>}</article>)}</div>
    {!data.rows.length && <p className="subtle">{onlyChanges ? 'No passage differences in these saved revisions.' : 'Both tellings are empty.'}</p>}
    <div className="branch-tool-actions"><button className="button" disabled={!previous.length} onClick={back}>Previous page</button><span className="subtle">{data.rows.length ? `Passages ${firstVisible + 1}–${data.rows.at(-1)!.index + 1} of ${data.total}` : `${data.total} passages`}</span><button className="button" disabled={data.next_offset === null} onClick={() => data.next_offset !== null && go(data.next_offset)}>Next page</button></div>
  </>}</section>
}

function Passage({ source, passage, side, onOpen, storyId, comparisonId, sourceSide }: { source: ComparisonSource; passage: ComparedPassage | null; side: string; onOpen: OpenPassage; storyId: string; comparisonId: string; sourceSide: 'left' | 'right' }) {
  const prose = useRef<HTMLParagraphElement>(null)
  const prepare = () => {
    const selection = selectedInline(prose.current, passage!.text)
    return { storyId, label: `${source.name} · saved revision ${source.revision}`, text: selection.text,
      source: { kind: 'comparison-text' as const, comparison_id: comparisonId, side: sourceSide, node_id: passage!.node_id, selection } }
  }
  return <section className="compared-passage" aria-label={`${side}: ${source.name}`}><p className="subtle comparison-source-label">{source.name} · r{source.revision}{passage ? ` · ${passage.role}` : ''}</p>{!passage ? <p className="subtle">No passage at this point.</p> : <>{passage.removed ? <><p className="subtle">Omitted from this telling.</p><details><summary>View omitted text</summary><p className="comparison-prose">{passage.omitted_text || 'Original text is unavailable.'}</p></details></> : <p ref={prose} className="comparison-prose">{passage.changes.map((change, index) => change.kind === 'removed' ? <del key={index}>{change.text}</del> : change.kind === 'added' ? <ins key={index}>{change.text}</ins> : <span key={index}>{change.text}</span>)}</p>}<button className="text-button" onClick={() => onOpen(source.branch_id, passage.node_id)}>Open source passage</button>{!passage.removed && <SendToCompanionButton prepare={prepare} />}</>}</section>
}
