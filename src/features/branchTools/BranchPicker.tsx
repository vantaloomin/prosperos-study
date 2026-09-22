import { useMemo, useState } from 'react'
import type { BranchSummary } from '../../types'

/** Bound option rendering even for Stories with thousands of tellings. */
export function BranchPicker({ branches, value, onChange, label, empty = 'Choose a telling', excluded = [] }: { branches: BranchSummary[]; value: string; onChange: (id: string) => void; label: string; empty?: string; excluded?: string[] }) {
  const [query, setQuery] = useState('')
  const options = useMemo(() => {
    const omitted = new Set(excluded)
    const candidates = branches.filter(branch => !omitted.has(branch.id) && branch.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
    const page = candidates.slice(0, 50)
    const selected = branches.find(branch => branch.id === value)
    if (selected && !page.some(branch => branch.id === value)) page.unshift(selected)
    return { page, total: candidates.length }
  }, [branches, query, excluded, value])
  return <div className="branch-picker"><label className="field"><span>{label}</span>{branches.length > 50 && <input type="search" aria-label={`Find ${label.toLowerCase()}`} value={query} onChange={event => setQuery(event.target.value)} placeholder="Filter by name…" />}<select aria-label={label} value={value} onChange={event => onChange(event.target.value)}><option value="">{empty}</option>{options.page.map(branch => <option key={branch.id} value={branch.id}>{branch.name} · r{branch.revision}{branch.curation?.favorite ? ' · favorite' : ''}{branch.curation?.archived ? ' · archived' : ''} · {branch.id.slice(-6)}</option>)}</select></label>{options.total > 50 && <small className="subtle">Showing the first 50 matches. Filter by name to find another telling.</small>}</div>
}
