import { ErrorNotice } from '../../components/Feedback'
import { useWritingVersion } from './useWritingResources'
import type { WritingKind, WritingResource } from './types'

export function WritingSelect({ label, kind, value, resources, inherit, draftOnly, recipePurpose, onChange }: { label: string; kind: WritingKind; value: string; resources: WritingResource[]; inherit?: string; draftOnly?: boolean; recipePurpose?: 'draft' | 'revise'; onChange: (value: string) => void }) {
  const selected = useWritingVersion(value)
  const options = resourceOptions(resources, selected.data, kind, value, draftOnly ? 'draft' : recipePurpose)
  const missing = value !== 'none' && value !== 'inherit' && !options.some(item => item.id === value)
  return <label className="field"><span>{label}</span><select aria-label={label} value={value} onChange={event => onChange(event.target.value)}>{inherit && <option value="inherit">{inherit}</option>}<option value="none">No {kind === 'style' ? 'style profile' : 'recipe'}</option>{missing && <option value={value}>{selected.error ? 'Selected version unavailable' : 'Loading selected version…'}</option>}{options.map(item => <option key={item.id} value={item.id}>{item.name} · v{item.number}{item.archived ? ' · archived' : ''}</option>)}</select><ErrorNotice message={selected.error?.message} /></label>
}

function resourceOptions(resources: WritingResource[], selected: WritingResource | undefined, kind: WritingKind, value: string, purpose?: 'draft' | 'revise') {
  const values = [...resources]
  if (selected && !values.some(item => item.id === selected.id)) values.unshift(selected)
  return values.filter(item => item.kind === kind && (item.id === value || available(item, purpose)))
}

function available(item: WritingResource, purpose?: 'draft' | 'revise') {
  if (item.archived) return false
  return !purpose || !('purpose' in item.content) || item.content.purpose === purpose
}
