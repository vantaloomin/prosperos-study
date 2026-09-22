import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Plus, Search, Users } from 'lucide-react'
import { api } from '../../api'
import { Empty, ErrorNotice, Loading } from '../../components/Feedback'
import type { AssetKind, AssetVersion, Selection } from '../../types'
import { AssetEditor } from './AssetEditor'
import { assetLabel, libraryKind } from './kinds'
import { artworkUrl } from './artworkUrl'

const LibraryImport = lazy(() => import('./LibraryImport').then((module) => ({ default: module.LibraryImport })))
const WritingLibrary = lazy(() => import('../writing/WritingLibrary').then(module => ({ default: module.WritingLibrary })))
const Migration = lazy(() => import('../migration/Migration').then(module => ({ default: module.Migration })))
const InspirationLibrary = lazy(() => import('../inspiration/InspirationLibrary').then(module => ({ default: module.InspirationLibrary })))

export function Library({ onOpen }: { onOpen: (selection: Selection) => void }) {
  const { data: assets = [], isPending, error } = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<AssetKind | 'all'>('all')
  const [editor, setEditor] = useState<AssetVersion | 'new' | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [migrationOpen, setMigrationOpen] = useState(false)
  const [section, setSection] = useState<'assets' | 'writing' | 'inspiration'>('assets')
  const visible = assets.filter((asset) => (filter === 'all' || libraryKind(asset.kind) === filter) && asset.name.toLowerCase().includes(search.toLowerCase()))
  return <main className="page library-page">
    <LibraryHeading writing={section !== 'assets'} onImport={() => setImportOpen(true)} onMigrate={() => setMigrationOpen(true)} onCreate={() => setEditor('new')} />
    <div className="library-toolbar"><div className="tabs library-filter-tabs" aria-label="Library filter">{(['all', 'character', 'lorebook'] as const).map((kind) => <button key={kind} aria-pressed={section === 'assets' && filter === kind} onClick={() => { setFilter(kind); setSection('assets') }}>{({ all: 'Everything', character: 'Characters', lorebook: 'Canon' })[kind]}</button>)}<button aria-pressed={section === 'writing'} onClick={() => setSection('writing')}>Styles & recipes</button><button aria-pressed={section === 'inspiration'} onClick={() => setSection('inspiration')}>Inspiration</button></div>{section === 'assets' && <label className="search"><Search size={15} /><input aria-label="Search library" placeholder="Search your library" value={search} onChange={(e) => setSearch(e.target.value)} /></label>}</div>
    <ErrorNotice message={error?.message} />
    <LibrarySection section={section} pending={isPending} assets={visible} onSelect={setEditor} />
    {editor && <AssetEditor asset={editor === 'new' ? undefined : editor} initialKind={filter === 'all' ? undefined : filter} onClose={() => setEditor(null)} />}
    {importOpen && <Suspense fallback={<Loading label="Opening the importer…" />}><LibraryImport onClose={() => setImportOpen(false)} /></Suspense>}
    {migrationOpen && <Suspense fallback={<Loading label="Opening migration…" />}><Migration onClose={() => setMigrationOpen(false)} onOpen={onOpen} /></Suspense>}
  </main>
}

function LibrarySection({ section, pending, assets, onSelect }: { section: string; pending: boolean; assets: AssetVersion[]; onSelect: (value: AssetVersion) => void }) {
  if (section === 'writing') return <Suspense fallback={<Loading label="Opening styles & recipes…" />}><WritingLibrary /></Suspense>
  if (section === 'inspiration') return <Suspense fallback={<Loading label="Opening inspiration decks…" />}><InspirationLibrary /></Suspense>
  return <LibraryItems pending={pending} assets={assets} onSelect={onSelect} />
}

function LibraryHeading({ writing, onImport, onMigrate, onCreate }: { writing: boolean; onImport: () => void; onMigrate: () => void; onCreate: () => void }) {
  return <header className="page-heading"><div><span className="eyebrow">YOUR CREATIVE LIBRARY</span><h1>Your library</h1><p>People, places, and the way you tell their stories.</p></div><div className="library-actions"><button className="button" onClick={onMigrate}>Migrate writing</button>{!writing && <><button className="button" onClick={onImport}>Import file</button><button className="button primary" onClick={onCreate}><Plus size={16} />Create new</button></>}</div></header>
}

function LibraryItems({ pending, assets, onSelect }: { pending: boolean; assets: AssetVersion[]; onSelect: (asset: AssetVersion) => void }) {
  if (pending) return <Loading label="Opening the library…" />
  if (!assets.length) return <Empty title="Every world begins somewhere."><p>Create a character or Canon collection. Bring it into any story, with earlier versions safely kept.</p></Empty>
  return <div className="library-grid">{assets.map((asset) => <button className={`asset-card ${asset.kind}`} key={asset.asset_id} onClick={() => onSelect(asset)}><div className="asset-monogram">{asset.content.artwork_sha256 ? <img src={artworkUrl(asset.content.artwork_sha256, 'thumbnail')} alt="" loading="lazy" decoding="async" /> : { character: <Users />, lorebook: <BookOpen />, persona: <Users /> }[asset.kind]}</div><div className="asset-card-body"><span className="eyebrow">{assetLabel(asset.kind)} <span className="version">v{asset.number}</span></span><h2>{asset.name}</h2>{asset.restored_at && <small>Restored {new Date(asset.restored_at).toLocaleString()}</small>}<p>{asset.content.text || 'Ready for a little more detail.'}</p></div><span className="asset-card-footer">Open & edit <span>↗</span></span></button>)}</div>
}
