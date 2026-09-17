import { Archive, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import type { StorySummary } from '../../types'

interface Props { stories: StorySummary[]; selected: string; onSelect: (id: string) => void; onNew: () => void }

export function StoryList({ stories, selected, onSelect, onNew }: Props) {
  const [search, setSearch] = useState('')
  const [archived, setArchived] = useState(false)
  const visible = stories.filter((story) => story.archived === archived && story.title.toLowerCase().includes(search.toLowerCase()))
  return <aside className="story-list" aria-label="Stories">
    <header><h2>Stories</h2><button className="icon-button" onClick={onNew} aria-label="New story"><Plus /></button></header>
    <label className="search"><Search size={15} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a story" aria-label="Find a story" /></label>
    <div className="story-items">
      {visible.map((story) => <button key={story.id} className={`story-row ${story.id === selected ? 'selected' : ''}`} onClick={() => onSelect(story.id)}>
        <span>{story.title}</span><small>{story.premise || 'An unwritten possibility'}</small>{story.restored_at && <small>Restored {new Date(story.restored_at).toLocaleString()}</small>}
      </button>)}
      {visible.length === 0 && <p className="subtle list-empty">{archived ? 'No archived stories.' : 'Your stories will live here.'}</p>}
    </div>
    <footer><button className="text-button" onClick={() => setArchived(!archived)}><Archive size={15} />{archived ? 'Back to stories' : 'Archived stories'}</button><div className="study-signature"><span>Prospero’s Study</span><small>Every story has its stage.</small></div></footer>
  </aside>
}
