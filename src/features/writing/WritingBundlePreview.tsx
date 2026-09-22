import { UnsupportedSettings } from './UnsupportedSettings'
import type { BundleMappings, BundleReport, BundleResource, MappingOption } from './bundleTypes'

export function BundleResources({ resources }: { resources: BundleResource[] }) {
  return <div className="form-stack">{resources.map(item => <article className="writing-resource-card" key={item.key}><span className="eyebrow">{item.kind === 'style' ? 'Style profile' : 'Writing recipe'}</span><h3>{item.name}</h3><p>{item.description}</p><details><summary>Inspect supported settings and samples</summary><pre className="writing-json">{JSON.stringify(item.content, null, 2)}</pre></details><UnsupportedSettings value={item.unsupported} /></article>)}</div>
}

export function BundleMappingsView({ report, value, onChange }: { report: BundleReport; value: BundleMappings; onChange: (value: BundleMappings) => void }) {
  return <section className="form-stack"><h3>Local dependency mappings</h3>{report.dependencies.length === 0 && <p className="subtle">This bundle needs no local mappings.</p>}{report.dependencies.map(reference => <label className="field" key={reference.key}><span>{reference.name} · {reference.kind}</span><select aria-label={`Map ${reference.name}`} value={mappingValue(value, reference.key)} onChange={event => onChange(changedMapping(value, reference.key, event.target.value))}><option value="unmapped">Choose a local mapping…</option><option value="default">{defaultLabel(reference.kind)}</option>{report.options[reference.kind].filter(item => reference.kind !== 'table' || item.table_id === reference.table_id).map(option => <option key={option.id} value={option.id}>{optionLabel(option)}</option>)}</select></label>)}</section>
}

function mappingValue(value: BundleMappings, key: string) {
  return key in value ? value[key] ?? 'default' : 'unmapped'
}

function changedMapping(value: BundleMappings, key: string, choice: string) {
  const next = { ...value }
  if (choice === 'unmapped') delete next[key]
  else next[key] = choice === 'default' ? null : choice
  return next
}

function defaultLabel(kind: string) {
  if (kind === 'model') return 'Use Story / workspace task default'
  return kind === 'style' ? 'No style profile' : 'Pin the current local table version'
}

function optionLabel(option: MappingOption) { return option.number ? `${option.name} · v${option.number}` : option.name }
