import { assetLabel, libraryKind } from './kinds'
import { useState } from 'react'
import { Field, TextField } from '../../components/Fields'
import type { AssetContent, AssetVersion } from '../../types'
import { CharacterFields } from './CharacterFields'
import { CanonMemory } from './CanonMemory'
import { ArtworkField } from './ArtworkField'
import { MarkdownSource } from './MarkdownSource'
import { VersionDiff } from './VersionDiff'
import { ImportedArtworkChoice } from './ImportedAssets'
import type { ImportAsset, ImportChoice, ImportDuplicate, ImportPreview } from './importTypes'
import { ImportDuplicates } from './ImportDuplicates'

export function ImportCompatibility({ preview }: { preview: ImportPreview }) {
  const isCard = preview.drafts.some(draft => draft.kind === 'character')
  return <section className="import-compatibility" aria-label="Import compatibility"><h3>What becomes part of your world</h3>
    <p>{isCard ? 'The edited character fields and Canon overview below can guide the writer. Greetings stay optional.' : 'The reviewed Markdown below becomes this Canon collection’s world knowledge.'} Nothing is added to a Story automatically.</p>
    {preview.issues.length > 0 && <ul>{preview.issues.map((issue, index) => <li key={`${issue.path}-${index}`}>{issue.message}</li>)}</ul>}
    <ImportMapping mapping={preview.mapping} />
    <p>{isCard ? 'Originals, unknown metadata and converted documents stay available as source material. Imported instructions never replace your application prompts.' : 'Your original source file stays available after later edits.'}</p>
  </section>
}

function ImportMapping({ mapping }: { mapping: ImportPreview['mapping'] }) {
  if (!mapping?.length) return null
  const labels = { mapped: 'Proposed field', review: 'Review before using', reference: 'Reference only' }
  return <details><summary>How this file maps to the Study</summary><ul>{mapping.map((item, index) => <li key={index}><strong>{item.source}</strong> → {item.target}. <span className="subtle">{labels[item.handling]}.</span></li>)}</ul></details>
}

export function ImportChoiceEditor({ choice, assets, importedAssets, duplicates = [], hasBatchDuplicate = false, onChange, onBusy }: { choice: ImportChoice; assets: AssetVersion[]; importedAssets?: ImportAsset[]; duplicates?: ImportDuplicate[]; hasBatchDuplicate?: boolean; onChange: (patch: Partial<ImportChoice>) => void; onBusy: (busy: boolean) => void }) {
  const contentChange = (patch: Partial<AssetContent>) => onChange({ content: { ...choice.content, ...patch } })
  return <section className="import-choice">
    <label className="check-row"><input type="checkbox" checked={choice.included} onChange={(event) => onChange({ included: event.target.checked })} /><strong>Publish {assetLabel(choice.kind)}</strong></label>
    {choice.included && <div className="form-stack character-advanced">
      <ImportTarget choice={choice} assets={assets} onChange={onChange} />
      <ImportDuplicates choice={choice} matches={duplicates.filter(item => item.part === choice.part)} hasBatchDuplicate={hasBatchDuplicate} onChange={onChange} />
      <Field label={`${choice.kind === 'character' ? 'Character' : 'Canon collection'} name`} value={choice.name} maxLength={120} onChange={(event) => onChange({ name: event.target.value })} />
      {choice.kind === 'character' && <ImportedArtworkChoice assets={importedAssets} value={choice.content.artwork_sha256} onChange={(artwork_sha256) => contentChange({ artwork_sha256 })} />}
      <ArtworkField value={choice.content.artwork_sha256} onChange={(artwork_sha256) => contentChange({ artwork_sha256 })} onBusy={onBusy} />
      <TextField label={choice.kind === 'character' ? 'Character & background' : 'Canon overview · Markdown'} value={choice.content.text ?? ''} rows={6} onChange={(event) => contentChange({ text: event.target.value })} />
      {choice.kind === 'character' && <details className="advanced-settings"><summary>Voice, greetings & other character fields</summary><div className="character-advanced"><CharacterFields content={choice.content} onChange={contentChange} /></div></details>}
      <ImportCanonFields choice={choice} onChange={onChange} />
      {choice.target && <ImportDifference choice={choice} target={choice.target} />}
    </div>}
  </section>
}

function ImportTarget({ choice, assets, onChange }: { choice: ImportChoice; assets: AssetVersion[]; onChange: (patch: Partial<ImportChoice>) => void }) {
  const available = assets.filter((asset) => libraryKind(asset.kind) === libraryKind(choice.kind))
  const current = available.find((asset) => asset.asset_id === choice.target?.asset_id)
  return <><label className="field"><span>{choice.kind === 'character' ? 'Character destination' : 'Canon collection destination'}</span>
    <select aria-label={choice.kind === 'character' ? 'Character destination' : 'Canon collection destination'} value={choice.target?.asset_id ?? ''} onChange={(event) => onChange({ target: available.find((asset) => asset.asset_id === event.target.value), sourceHash: null })}>
      <option value="">Create a new Library item</option>{available.map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.name} · publish after v{asset.number}</option>)}
    </select></label>
    {choice.target && <p className="subtle">A new version of {choice.target.name} will be created. Earlier versions and existing Story selections stay preserved.</p>}
    {current && current.id !== choice.target?.id && <p className="subtle" role="status">A newer target version is available. <button className="text-button" onClick={() => onChange({ target: current, sourceHash: null })}>Review target v{current.number}</button></p>}
  </>
}

function ImportDifference({ choice, target }: { choice: ImportChoice; target: AssetVersion }) {
  const [open, setOpen] = useState(false)
  return <details className="advanced-settings" onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Compare with current Library version</summary>
    {open && <VersionDiff before={target} after={{ ...target, number: target.number + 1, name: choice.name, content: choice.content, note: 'Import proposal' }} />}
  </details>
}

function ImportCanonFields({ choice, onChange }: { choice: ImportChoice; onChange: (patch: Partial<ImportChoice>) => void }) {
  if (choice.kind !== 'lorebook') return null
  return <><CanonMemory name={choice.name} content={choice.content} asset={choice.target} onChange={(patch) => onChange({ content: { ...choice.content, ...patch } })} />
    {choice.target && <MarkdownSource key={choice.target.id} asset={choice.target} text={choice.content.text ?? ''} sourceHash={choice.sourceHash} onUse={(text, sourceHash) => onChange({ content: { ...choice.content, text }, sourceHash })} />}
  </>
}
