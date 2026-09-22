import { lazy, Suspense, useRef, useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { AssetKind, AssetVersion } from '../../types'
import { AdoptionDialog } from './AdoptionDialog'
import { AssetHistory, AssetUsage } from './AssetHistory'
import { CharacterFields } from './CharacterFields'
import { CanonMemory } from './CanonMemory'
import { assetLabel, libraryKind } from './kinds'
import { MarkdownSource } from './MarkdownSource'
import { ImportedSources } from './ImportSources'
import { EntrySources } from './EntrySources'
import { LoreEntries } from './LoreEditor'
import { changeAssetKind, migrateAssetDraft, versionDraft, type AssetDraft } from './versionChanges'
import { AuthoringLauncher } from '../authoring/AuthoringLauncher'
import { ArtworkField } from './ArtworkField'
import type { ImportPreview } from './importTypes'

const LibraryImport = lazy(() => import('./LibraryImport').then((module) => ({ default: module.LibraryImport })))
const VersionedTextEdit = lazy(() => import('../textEdits/VersionedTextEdit').then(module => ({ default: module.VersionedTextEdit })))

export function AssetEditor({ asset, initialKind, onClose, onSaved }: { asset?: AssetVersion; initialKind?: AssetKind; onClose: () => void; onSaved?: (version: AssetVersion) => void }) {
  const draftKey = assetDraftKey(asset, initialKind)
  const [saved, setDraft] = usePersistent(draftKey, versionDraft(asset, initialKind))
  const migrated = migrateAssetDraft(saved, asset)
  const draft = { ...migrated, kind: libraryKind(migrated.kind) }
  const [newDraftId] = useState(() => draft.assistance_id ?? crypto.randomUUID())
  const [returnFocus] = useState(() => document.activeElement as HTMLElement | null)
  const [published, setPublished] = useState<AssetVersion | null>(null)
  const [push, setPush] = useState(false)
  const [card, setCard] = useState<ImportPreview | null>(null)
  const [artworkBusy, setArtworkBusy] = useState(false)
  const [scopedEdit, setScopedEdit] = useState<AssetVersion | null>(null)
  const editorRoot = useRef<HTMLDivElement>(null)
  const action = useAction()
  const patch = (change: Partial<AssetDraft>) => setDraft({ ...draft, ...change })
  const contentPatch = (change: Partial<AssetDraft['content']>) => patch({ content: { ...draft.content, ...change } })
  const save = () => action.run(async () => {
    const content = draft.content
    const body = { name: draft.name, content, note: draft.note }
    const next = asset
      ? await api<AssetVersion>(`/library/${asset.asset_id}/versions`, { ...body, expected_version_id: asset.id, expected_source_hash: draft.source_hash, expected_entry_hashes: draft.entry_hashes })
      : await api<AssetVersion>('/library', { ...body, kind: draft.kind })
    localStorage.removeItem(draftKey)
    onSaved?.(next)
    if (push) setPublished(next)
    else onClose()
  })
  if (published) return <AdoptionDialog version={published} onClose={onClose} focusOnClose={() => returnFocus} />
  if (scopedEdit) return <Suspense fallback={<Loading />}><VersionedTextEdit source={{ kind: 'library-field', asset_id: scopedEdit.asset_id }} expectedEdition={scopedEdit.id} onClose={onClose} focusOnClose={() => returnFocus} /></Suspense>
  if (card) return <Suspense fallback={<Loading label="Opening card review…" />}><LibraryImport initialImportId={card.id} target={asset} onClose={() => setCard(null)} onPublishedClose={onClose} focusOnClose={() => editorRoot.current?.querySelector('input') ?? null} focusOnPublishedClose={() => returnFocus} /></Suspense>
  return <Modal open onClose={onClose} title={asset ? `Edit ${asset.name}` : 'A new addition'} description="Published versions stay in the library. Existing stories keep the versions they already use." wide>
    <div ref={editorRoot} className="dialog-body editor-columns"><div className="form-stack">
      {!asset && <label className="field"><span>Type</span><select value={draft.kind} onChange={(e) => setDraft(changeAssetKind(draft, e.target.value as AssetKind))}><option value="character">Character</option><option value="lorebook">Canon collection</option></select></label>}
      <Field label="Name" value={draft.name} onChange={(e) => patch({ name: e.target.value })} maxLength={120} autoFocus />
      <EditorArtwork draft={draft} onChange={contentPatch} onCard={setCard} onBusy={setArtworkBusy} />
      <AssetFields draft={draft} asset={asset} versionId={asset?.id} onChange={contentPatch} />
      <AuthoringLauncher draft={draft} draftId={asset ? draftKey : newDraftId} asset={asset} onChange={setDraft} />
      <BookSources asset={asset} draft={draft} onChange={(change) => { action.clearError(); patch(change) }} />
      <Field label="Version note" value={draft.note} onChange={(e) => patch({ note: e.target.value })} placeholder="What changed? (optional)" />
      <ImportedSources asset={asset} />
      <ErrorNotice message={action.error} />
    </div><aside className="editor-aside"><span className="eyebrow">A SHARED LIBRARY</span><h3>Let your worlds grow.</h3><p>Use this {assetLabel(draft.kind).toLowerCase()} in several stories. A new version gives future stories the latest details without changing the past.</p>{asset && <><ScopedTextButton draft={draft} asset={asset} busy={action.busy} artworkBusy={artworkBusy} onOpen={() => setScopedEdit(asset)} /><AssetUsage asset={asset} /><AssetHistory asset={asset} onUse={(version) => patch({ ...versionDraft(version), note: `Restored from v${version.number}` })} /></>}</aside></div>
    <AssetFooter push={push} onPush={setPush} name={draft.name} busy={action.busy} artworkBusy={artworkBusy} onSave={save} />
  </Modal>
}

function assetDraftKey(asset?: AssetVersion, initialKind?: AssetKind): string {
  return `roleplay:asset-draft:${asset?.id ?? (initialKind ? `new-${initialKind}` : 'new')}`
}

function ScopedTextButton({ draft, asset, busy, artworkBusy, onOpen }: { draft: AssetDraft; asset: AssetVersion; busy: boolean; artworkBusy: boolean; onOpen: () => void }) {
  const dirty = draft.name !== asset.name || draft.note !== '' || JSON.stringify(draft.content) !== JSON.stringify(asset.content)
  return <div className="form-stack"><button className="button" disabled={dirty || busy || artworkBusy} onClick={onOpen}>Review a scoped text change</button>{dirty && <p className="subtle">Publish the current draft before starting a separate text-change proposal.</p>}</div>
}

function EditorArtwork({ draft, onChange, onCard, onBusy }: { draft: AssetDraft; onChange: (change: Partial<AssetDraft['content']>) => void; onCard: (preview: ImportPreview) => void; onBusy: (busy: boolean) => void }) {
  return <ArtworkField key={draft.kind} value={draft.content.artwork_sha256} onChange={(artwork_sha256) => onChange({ artwork_sha256 })} onCard={draft.kind === 'character' ? onCard : undefined} onBusy={onBusy} />
}

function AssetFields({ draft, asset, versionId, onChange }: { draft: AssetDraft; asset?: AssetVersion; versionId?: string; onChange: (change: Partial<AssetDraft['content']>) => void }) {
  return <><TextField label={{ character: 'Character & background', lorebook: 'World knowledge · Markdown', persona: 'Character & background' }[draft.kind]} hint={draft.kind === 'lorebook' ? 'Headings, lists and ordinary prose. Saving creates a Markdown source file and a preserved version.' : undefined} value={draft.content.text ?? ''} onChange={(e) => onChange({ text: e.target.value })} rows={10} maxLength={100000} placeholder="Details, boundaries, relationships, and things worth remembering…" />
    {draft.kind === 'character' && <CharacterFields content={draft.content} onChange={onChange} />}
    {draft.kind === 'lorebook' && <><LoreEntries content={draft.content} versionId={versionId} onChange={onChange} /><CanonMemory name={draft.name} content={draft.content} asset={asset} onChange={onChange} /></>}
  </>
}

function BookSources({ asset, draft, onChange }: { asset?: AssetVersion; draft: AssetDraft; onChange: (change: Partial<AssetDraft>) => void }) {
  if (asset?.kind !== 'lorebook') return null
  return <><MarkdownSource asset={asset} text={draft.content.text ?? ''} sourceHash={draft.source_hash} onUse={(text, source_hash) => onChange({ content: { ...draft.content, text }, source_hash })} />
    <EntrySources asset={asset} content={draft.content} hashes={draft.entry_hashes ?? {}} onUse={(content, entry_hashes) => onChange({ content, entry_hashes })} /></>
}

function AssetFooter({ push, onPush, name, busy, artworkBusy, onSave }: { push: boolean; onPush: (push: boolean) => void; name: string; busy: boolean; artworkBusy: boolean; onSave: () => void }) {
  return <footer className="dialog-footer editor-footer"><label className="check-row"><input type="checkbox" checked={push} onChange={(event) => onPush(event.target.checked)} />Review an update to all existing stories</label><button className="button primary" onClick={onSave} disabled={artworkBusy || !name.trim()} aria-disabled={busy || artworkBusy || !name.trim()}>{busy ? 'Saving…' : 'Save new version'}</button></footer>
}
