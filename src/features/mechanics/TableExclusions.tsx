import { useState } from 'react'
import type { RngSettings, TableDefinition, TableVersion } from './types'

function available(definitions: Map<string, TableDefinition>, settings: RngSettings, key: string, trail: string[] = []): string[] {
  const definition = definitions.get(key)
  if (!definition || settings.disabled_tables.includes(key) || trail.includes(key)) return []
  const rows = definition.rows.filter((row) => !settings.excluded_rows[key]?.includes(row.id))
  if (key === 'handling' && !settings.subresults) return rows.map((row) => row.id)
  return rows.filter((row) => !row.child || available(definitions, settings, row.child, [...trail, key]).length).map((row) => row.id)
}

export function TableExclusions({ tables, settings, onChange }: { tables: TableVersion[]; settings: RngSettings; onChange: (change: Partial<RngSettings>) => void }) {
  const [key, setKey] = useState('narrative-push')
  const table = tables.find((item) => item.table_id === key)
  if (!table) return null
  const excluded = settings.excluded_rows[key] ?? []
  const definitions = new Map(tables.map((item) => [item.table_id, item.definition]))
  const enabled = available(definitions, settings, key)
  const weight = table.definition.rows.filter((row) => enabled.includes(row.id)).reduce((sum, row) => sum + row.high - row.low + 1, 0)
  const toggleTable = () => onChange({ disabled_tables: settings.disabled_tables.includes(key) ? settings.disabled_tables.filter((item) => item !== key) : [...settings.disabled_tables, key] })
  const toggleRow = (id: string) => onChange({ excluded_rows: { ...settings.excluded_rows, [key]: excluded.includes(id) ? excluded.filter((item) => item !== id) : [...excluded, id] } })
  return <section className="form-stack"><div><h3>Table and result controls</h3><p className="subtle">Exclusions preserve remaining weights. Disabled child tables remove their parent result. These percentages describe this table's base draw, before modifiers or pacing suppression.</p></div><label className="field"><span>Table to configure</span><select value={key} onChange={(e) => setKey(e.target.value)}>{tables.map((item) => <option key={item.table_id} value={item.table_id}>{item.definition.name}</option>)}</select></label><label className="check-row"><input type="checkbox" checked={!settings.disabled_tables.includes(key)} onChange={toggleTable} />Enable this table</label><div className="odds-list">{table.definition.rows.map((row) => <label className="odds-row" key={row.id}><input type="checkbox" checked={!excluded.includes(row.id)} onChange={() => toggleRow(row.id)} /><span>{row.label}<small>{row.low}–{row.high}{row.child && ` · requires ${row.child}`}</small></span><strong>{enabled.includes(row.id) ? (100 * (row.high - row.low + 1) / weight).toFixed(1) : '0.0'}%</strong></label>)}</div><ExceptionalResults definition={table.definition} excluded={excluded} onToggle={toggleRow} />{!weight && <p className="subtle">No enabled outcomes remain. This table will be skipped.</p>}</section>
}

function ExceptionalResults({ definition, excluded, onToggle }: { definition: TableDefinition; excluded: string[]; onToggle: (id: string) => void }) {
  const results = [definition.low_overflow, definition.high_overflow].filter((result) => result !== null)
  if (!results.length) return null
  return <div className="form-stack"><h4>Exceptional modified outcomes</h4><p className="subtle">These occur only when modifiers take a result beyond the table. Their chance depends on the attempt. Excluded outcomes are suppressed without a replacement roll or domain change.</p>{results.map((result) => <label className="check-row" key={result.id}><input type="checkbox" checked={!excluded.includes(result.id)} onChange={() => onToggle(result.id)} /><span>{result.label}<small>{result.instruction}</small></span></label>)}</div>
}
