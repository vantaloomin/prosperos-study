import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Plus, Search, Users } from 'lucide-react'
import { api } from '../../api'
import { Empty, ErrorNotice, Loading } from '../../components/Feedback'
import type { AssetKind, AssetVersion } from '../../types'
import { AssetEditor } from './AssetEditor'
import { assetLabel, libraryKind } from './kinds'
import { artworkUrl } from './artworkUrl'

const LibraryImport = lazy(() => import('./LibraryImport').then((module) => ({ default: module.LibraryImport })))
const WritingLibrary = lazy(() => import('../writing/WritingLibrary').then(module => ({ default: module.WritingLibrary })))

export function Library() {
  const { data: assets = [], isPending, error } = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<AssetKind | 'all'>('all')
  const [editor, setEditor] = useState<AssetVersion | 'new' | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [writing, setWriting] = useState(false)
  const visible = assets.filter((asset) => (filter === 'all' || libraryKind(asset.kind) === filter) && asset.name.toLowerCase().includes(search.toLowerCase()))
  return <main className="page library-page">
    <LibraryHeading writing={writing} onImport={() => setImportOpen(true)} onCreate={() => setEditor('new')} />
    <div className="library-toolbar"><div className="tabs" aria-label="Library filter">{(['all', 'character', 'lorebook'] as const).map((kind) => <button key={kind} aria-pressed={!writing && filter === kind} onClick={() => { setFilter(kind); setWriting(false) }}>{({ all: 'Everything', character: 'Characters', lorebook: 'Canon' })[kind]}</button>)}<button aria-pressed={writing} onClick={() => setWriting(true)}>Styles & recipes</button></div>{!writing && <label className="search"><Search size={15} /><input aria-label="Search library" placeholder="Search your library" value={search} onChange={(e) => setSearch(e.target.value)} /></label>}</div>
    <ErrorNotice message={error?.message} />
    {writing ? <Suspense fallback={<Loading label="Opening styles & recipes…" />}><WritingLibrary /></Suspense> : <LibraryItems pending={isPending} assets={visible} onSelect={setEditor} />}
    {editor && <AssetEditor asset={editor === 'new' ? undefined : editor} initialKind={filter === 'all' ? undefined : filter} onClose={() => setEditor(null)} />}
    {importOpen && <Suspense fallback={<Loading label="Opening the importer…" />}><LibraryImport onClose={() => setImportOpen(false)} /></Suspense>}
  </main>
}

function LibraryHeading({ writing, onImport, onCreate }: { writing: boolean; onImport: () => void; onCreate: () => void }) {
  return <header className="page-heading"><div><span className="eyebrow">YOUR CREATIVE LIBRARY</span><h1>Your library</h1><p>People, places, and the way you tell their stories.</p></div>{!writing && <div className="library-actions"><button className="button" onClick={onImport}>Import file</button><button className="button primary" onClick={onCreate}><Plus size={16} />Create new</button></div>}</header>
}

function LibraryItems({ pending, assets, onSelect }: { pending: boolean; assets: AssetVersion[]; onSelect: (asset: AssetVersion) => void }) {
  if (pending) return <Loading label="Opening the library…" />
  if (!assets.length) return <Empty title="Every world begins somewhere."><p>Create a character or Canon collection. Bring it into any story, with earlier versions safely kept.</p></Empty>
  return <div className="library-grid">{assets.map((asset) => <button className={`asset-card ${asset.kind}`} key={asset.asset_id} onClick={() => onSelect(asset)}><div className="asset-monogram">{asset.content.artwork_sha256 ? <img src={artworkUrl(asset.content.artwork_sha256, 'thumbnail')} alt="" loading="lazy" decoding="async" /> : { character: <Users />, lorebook: <BookOpen />, persona: <Users /> }[asset.kind]}</div><div className="asset-card-body"><span className="eyebrow">{assetLabel(asset.kind)} <span className="version">v{asset.number}</span></span><h2>{asset.name}</h2>{asset.restored_at && <small>Restored {new Date(asset.restored_at).toLocaleString()}</small>}<p>{asset.content.text || 'Ready for a little more detail.'}</p></div><span className="asset-card-footer">Open & edit <span>↗</span></span></button>)}</div>
}
