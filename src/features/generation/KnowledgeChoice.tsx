import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'

interface Decision { character_id?: string; kind: string; subject: string; stance: string; enabled: boolean }
export interface KnowledgeReceipt { subject: string; permitted_decisions: number; selected_decisions: number; source_count: number }

export function KnowledgeChoice({ branchId, value, onChange }: { branchId: string; value: string; onChange: (value: string) => void }) {
  const query = useQuery({ queryKey: ['memory-controls', branchId], queryFn: () => api<{ entries: Decision[]; characters: { id: string; name: string }[] }>('/branches/' + branchId + '/memory-controls') })
  const names = (query.data?.entries ?? []).filter(item => item.enabled && item.kind === 'knowledge').map(item => ({
    value: item.character_id ? 'character:' + item.character_id : 'name:' + item.subject,
    label: item.character_id ? (query.data?.characters.find(character => character.id === item.character_id)?.name ?? item.subject) + ' · Character ' + item.character_id.slice(0, 8) : item.subject + ' · name-only',
  }))
  const choices = new Map(names.map(item => [item.value, item.label]))
  if (value && !choices.has(value)) choices.set(value, 'Previously selected view (unavailable)')
  const label = choices.get(value) ?? 'Author'
  return <details className="advanced-settings"><summary>Writer knowledge view{': ' + label}</summary><div className="form-stack">
    <label className="field"><span id={'knowledge-view-label-' + branchId}>Evidence available to this writer</span><select aria-labelledby={'knowledge-view-label-' + branchId} value={value} onChange={event => onChange(event.target.value)}><option value="">Author view</option>{[...choices].map(([id, name]) => <option key={id} value={id}>{name}: permitted evidence only</option>)}</select></label>
    <p className="subtle">Character views use the exact excerpts assigned in Story memory as known, believed or uncertain. Does-not-know decisions take precedence. Review every excerpt: its entire text becomes available to that character.</p>
    {value && <p role="status" className="subtle">Only this character's granted excerpts and your instructions are sent. Canon and Character text require explicit grants from pinned editions. Private background, unassigned notes and chance are excluded. New prose needs a knowledge decision before automatic continuation; use Context budget to inspect the next request. Scene dialogue can use separate character briefings; the sidebar retains its author view.</p>}
    {!names.length && <p className="subtle">Add character knowledge in Story memory to create a character view.</p>}
    <ErrorNotice message={query.error?.message} />
  </div></details>
}

export function KnowledgeCoverage({ report }: { report: KnowledgeReceipt }) {
  return <div className="context-coverage"><p>Character evidence view: {report.subject}</p><p>{report.selected_decisions} of {report.permitted_decisions} permitted decisions; {report.source_count} exact source excerpts.</p><small>These counts describe permitted evidence only. Unassigned prose and reference text, private background and other characters' notes are excluded. Your editable writer prompt and explicit direction still apply. This controls supplied context; it cannot prevent model guesses or knowledge learned during training.</small></div>
}
