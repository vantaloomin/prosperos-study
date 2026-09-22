import type { Selection } from '../../types'
import { SkippedImports } from '../library/ImportDuplicates'
import type { BatchItem } from './batchTypes'

export function BatchResult({ item, onOpen }: { item: BatchItem; onOpen: (selection: Selection) => void }) {
  const result = item.result
  if (!result) return null
  return <section className="form-stack" role="status"><h4>{result.status === 'skipped' ? 'Duplicate left unchanged' : 'Saved migration result'}</h4>
    <p>This result is recorded. Returning to this item or retrying its publication does not import it again.</p><StoryResult item={item} onOpen={onOpen} />
    <ResourceResult item={item} /><SkippedImports skipped={result.skipped} />
    <p className="subtle">Story adoption and model selection remain separate deliberate actions. Source downloads and this result stay available from the queue.</p>
  </section>
}

function StoryResult({ item, onOpen }: { item: BatchItem; onOpen: (selection: Selection) => void }) {
  const result = item.result!
  const selection = result.story_id ? { storyId: result.story_id, branchId: result.branch_id ?? '' } : result.selection
  return <>{result.selected_messages !== undefined && <p>{result.selected_messages} messages imported in their selected order.</p>}{result.story_ids && <p>{result.story_ids.length} Stories restored as new copies.</p>}{selection?.storyId && <button className="button" onClick={() => onOpen(selection)}>Open imported Story</button>}</>
}

function ResourceResult({ item }: { item: BatchItem }) {
  const result = item.result!
  const resources = [...(result.versions ?? []), ...(result.resources ?? []), ...(result.resource ? [result.resource] : [])]
  return <>{resources.map((resource, index) => <p key={index}>{resource.name} · published v{resource.number}</p>)}{result.profile && <p>Separate profile copy: {result.profile.name}</p>}{result.activation && <p>{result.activation}</p>}</>
}
