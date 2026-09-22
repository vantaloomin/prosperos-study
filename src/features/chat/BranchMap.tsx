import { lazy, Suspense, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { GitBranch, Check, Search, MoreHorizontal, Star } from 'lucide-react'
import { Modal } from '../../components/Modal'
import { Loading } from '../../components/Feedback'
import type { BranchSummary } from '../../types'
import { branchRows, nextBranchIndex, type BranchRow } from './branchTree'
import { BranchCurationControls } from '../branchTools/BranchCuration'
import type { OpenPassage } from '../branchTools/types'
import '../branchTools/branchTools.css'

const BranchCompare = lazy(() => import('../branchTools/BranchCompare').then(module => ({ default: module.BranchCompare })))
const BranchSearch = lazy(() => import('../branchTools/BranchSearch').then(module => ({ default: module.BranchSearch })))
interface Props { storyId: string; branches: BranchSummary[]; selected: string; onSelect: (id: string) => void; onOpen: OpenPassage; onClose: () => void; openedAt: number }
const ROW_HEIGHT = 80
const OVERSCAN = 4

function useTreeViewport(rows: BranchRow[], selected: string) {
  const element = useRef<HTMLDivElement>(null)
  const [top, setTop] = useState(0)
  const [height, setHeight] = useState(500)
  const [focusId, setFocusId] = useState(selected)
  const focused = Math.max(0, rows.findIndex((row) => row.branch.id === focusId))
  const start = Math.max(0, Math.floor(top / ROW_HEIGHT) - OVERSCAN)
  const end = Math.min(rows.length, Math.ceil((top + height) / ROW_HEIGHT) + OVERSCAN)
  useLayoutEffect(() => {
    const node = element.current
    if (!node) return
    const observer = new ResizeObserver(() => setHeight(node.clientHeight))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  useLayoutEffect(() => {
    const node = element.current
    if (!node) return
    const position = focused * ROW_HEIGHT
    if (position < node.scrollTop || position + ROW_HEIGHT > node.scrollTop + node.clientHeight) node.scrollTop = position
    setTop(node.scrollTop)
  }, [focused, rows])
  const focusRow = (index: number) => {
    if (!rows[index]) return
    setFocusId(rows[index].branch.id)
    element.current?.focus()
  }
  return { element, start, end, focused, setTop, focusRow }
}

function BranchTree({ rows, selected, onSelect, onManage, openedAt }: { rows: BranchRow[]; selected: string; onSelect: (id: string) => void; onManage: (id: string) => void; openedAt: number }) {
  const { element, start, end, focused, setTop, focusRow } = useTreeViewport(rows, selected)
  useLayoutEffect(() => {
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => { if (element.current) element.current.dataset.mapReadyMs = (performance.now() - openedAt).toFixed(1) })
    })
    return () => cancelAnimationFrame(frame)
  }, [openedAt, element])
  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('.branch-tree-organize')) return
    if (event.key.toLowerCase() === 'o' && rows[focused]) { event.preventDefault(); onManage(rows[focused].branch.id); return }
    if (['Enter', ' '].includes(event.key) && rows[focused]) { event.preventDefault(); onSelect(rows[focused].branch.id); return }
    const next = nextBranchIndex(event.key, focused, rows)
    if (next < 0) return
    event.preventDefault()
    focusRow(next)
  }
  const focusedId = focused >= start && focused < end ? rows[focused]?.branch.id : undefined
  return <div ref={element} className="branch-tree-scroll" role="tree" tabIndex={0} aria-label="Branch map" aria-activedescendant={focusedId ? `branch-tree-${focusedId}` : undefined} onKeyDown={keyboard} onScroll={(event) => setTop(event.currentTarget.scrollTop)}>
    <div className="branch-tree-canvas" style={{ height: Math.max(140, rows.length * ROW_HEIGHT) }}>
      {rows.slice(start, end).map((row, offset) => <BranchTreeRow key={row.branch.id} row={row} index={start + offset} selected={selected} focused={rows[focused]?.branch.id === row.branch.id} onSelect={onSelect} onManage={onManage} />)}
      {!rows.length && <p className="subtle branch-empty">No branches match this name.</p>}
    </div>
  </div>
}

function BranchTreeRow({ row, index, selected, focused, onSelect, onManage }: { row: BranchRow; index: number; selected: string; focused: boolean; onSelect: (id: string) => void; onManage: (id: string) => void }) {
  const indent = Math.min(row.depth, 6) * 22
  return <div className="branch-tree-row" style={{ top: index * ROW_HEIGHT, paddingLeft: `calc(16px + min(${indent}px, 12vw))` }}>
    {row.depth > 0 && <svg className="branch-tree-connector" aria-hidden style={{ left: `calc(min(${indent}px, 12vw) - 2px)` }} width="18" height="80"><path d="M 1 0 V 40 H 18" /></svg>}
    <button id={`branch-tree-${row.branch.id}`} role="treeitem" tabIndex={-1} aria-level={row.depth + 1} aria-posinset={row.position} aria-setsize={row.siblings} aria-selected={row.branch.id === selected} data-focused={focused} className="branch-tree-node" onClick={() => onSelect(row.branch.id)}>
      {row.branch.curation?.favorite ? <Star size={16} aria-label="Favorite" /> : <GitBranch size={16} />}<span>{row.branch.name}<small>{row.branch.curation?.archived ? 'Archived · ' : ''}{row.depth ? `Depth ${row.depth.toLocaleString()} · from ${row.parentName}` : 'Where the story began'}</small></span>{row.branch.id === selected && <Check size={16} />}
    </button>
    <button className="icon-button branch-tree-organize" aria-label={`Organize ${row.branch.name}`} onClick={() => onManage(row.branch.id)}><MoreHorizontal size={17} /></button>
  </div>
}

export function BranchMap({ storyId, branches, selected, onSelect, onOpen, onClose, openedAt }: Props) {
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<'browse' | 'compare' | 'search'>('browse')
  const [filter, setFilter] = useState('active')
  const [managed, setManaged] = useState(selected)
  const management = useRef<HTMLHeadingElement>(null)
  const rows = useMemo(() => branchRows(branches), [branches])
  const filtered = useMemo(() => rows.filter(({ branch }) => branch.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) && (filter === 'all' || (filter === 'archived' ? branch.curation?.archived : !branch.curation?.archived && (filter !== 'favorites' || branch.curation?.favorite)))), [rows, search, filter])
  const managedBranch = branches.find(branch => branch.id === managed)
  const manage = (id: string) => { setManaged(id); management.current?.focus() }
  const select = (id: string) => { onSelect(id); onClose() }
  const open: OpenPassage = (branchId, nodeId) => { onOpen(branchId, nodeId); onClose() }
  return <Modal open onClose={onClose} title="Every path stays with you" description="Choose a branch to return to its own history and pinned library versions." wide>
    <div className="tabs branch-map-tabs" aria-label="Branch tools"><button aria-pressed={tab === 'browse'} onClick={() => setTab('browse')}>Tellings</button><button aria-pressed={tab === 'compare'} onClick={() => setTab('compare')}>Compare</button><button aria-pressed={tab === 'search'} onClick={() => setTab('search')}>Search prose</button></div>
    {tab === 'browse' && <div className="branch-map-browse">
    {managedBranch && <section className="branch-manage" aria-label="Organize telling"><div className="branch-tool-actions"><h3 ref={management} tabIndex={-1}>{managedBranch.name}{managedBranch.id === selected ? ' · currently open' : ''}</h3>{managedBranch.id !== selected && <button className="text-button" onClick={() => select(managedBranch.id)}>Open telling</button>}</div><BranchCurationControls key={managedBranch.id} branch={managedBranch} /></section>}
    <label className="branch-map-filters field"><span>Show tellings</span><select aria-label="Show tellings" value={filter} onChange={event => setFilter(event.target.value)}><option value="active">Active</option><option value="favorites">Favorites</option><option value="archived">Archived</option><option value="all">All tellings</option></select></label>
    <div className="branch-map-tools"><label className="search"><Search size={16} /><input aria-label="Find a branch" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a branch…" /></label><span className="subtle">{filtered.length.toLocaleString()} of {branches.length.toLocaleString()} paths</span></div>
    <BranchTree key={`${search}:${filter}`} rows={filtered} selected={selected} onSelect={select} onManage={manage} openedAt={openedAt} />
    <footer className="branch-map-help"><span>↑ ↓ explore · ← parent · → child · Enter opens · O organizes</span><span>Deep paths show their exact depth and parent.</span></footer>
    </div>}
    {tab === 'compare' && <Suspense fallback={<Loading label="Opening comparisons…" />}><BranchCompare storyId={storyId} branches={branches} selected={selected} onOpen={open} onSelect={select} /></Suspense>}
    {tab === 'search' && <Suspense fallback={<Loading label="Opening Story search…" />}><BranchSearch storyId={storyId} branches={branches} onOpen={open} /></Suspense>}
  </Modal>
}
