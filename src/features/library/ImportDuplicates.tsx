import { assetLabel } from './kinds'
import type { ImportChoice, ImportDuplicate, ImportResult } from './importTypes'

export function ImportDuplicates({ choice, matches, hasBatchDuplicate = false, onChange }: { choice: ImportChoice; matches: ImportDuplicate[]; hasBatchDuplicate?: boolean; onChange: (patch: Partial<ImportChoice>) => void }) {
  if (!matches.length && !hasBatchDuplicate) return null
  return <section className="import-compatibility"><h4>{matches.length ? 'Previously imported' : 'Matching queued'} {assetLabel(choice.kind)}</h4>{matches.map(item => <p key={item.version_id}>{item.name} · {item.match === 'exact-source' ? 'exact source file' : 'same proposed content; names and source metadata may differ'}</p>)}<p className="subtle">Showing up to 50 matching versions. This compares source proposals, not later edits to the Library item. Same names never select an update target.</p>{!choice.target && <label className="field"><span>{assetLabel(choice.kind)} duplicate decision</span><select aria-label={`${assetLabel(choice.kind)} duplicate decision`} value={choice.duplicate_action ?? 'skip'} onChange={event => onChange({ duplicate_action: event.target.value as 'skip' | 'new' })}><option value="skip">Skip if already imported</option><option value="new">Deliberately create another item</option></select></label>}</section>
}

export function SkippedImports({ skipped }: { skipped: ImportResult['skipped'] }) {
  if (!skipped?.length) return null
  return <section className="import-compatibility"><h4>Duplicates left unchanged</h4>{skipped.map(item => <p key={item.part}>{assetLabel(item.part)} skipped · Previously imported as {item.duplicates.map(match => match.name).join(', ')}.</p>)}<p className="subtle">A skipped Canon collection is not automatically linked to a newly imported character. Choose that existing collection explicitly in the character editor if needed.</p></section>
}
