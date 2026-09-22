import { BookOpen, Feather, GitBranch, ListChecks, MessageSquareText, PanelRight, SlidersHorizontal } from 'lucide-react'
import type { BranchCuration, Story } from '../../types'

interface Props {
  story: Story
  branchName: string
  curation?: BranchCuration
  context?: boolean
  side?: boolean
  tools?: boolean
  onTools?: () => void
  onMap: () => void
  onWorkflow?: () => void
  onManuscript?: () => void
  onDetails?: () => void
  onContext?: () => void
  onSide?: () => void
}

export function ChatHeading({ story, branchName, curation, context = false, side = false, tools = false, onTools, onMap, onWorkflow, onManuscript, onDetails, onContext, onSide }: Props) {
  const actions = <>
    <button className="icon-button" aria-label="Book workspace" disabled={!onManuscript} onClick={onManuscript}><BookOpen size={18} /><span className="action-label">Book</span></button>
    <button className="icon-button" aria-label="Writing tools" aria-pressed={tools} onClick={onTools}><Feather size={18} /><span className="action-label">Writing tools</span></button>
    <button className="icon-button" aria-label="Story workflow" disabled={!onWorkflow} onClick={onWorkflow}><ListChecks size={18} /><span className="action-label">Workflow</span></button>
    <button className="icon-button" aria-label="Story setup" disabled={!onDetails} onClick={onDetails}><SlidersHorizontal size={18} /><span className="action-label">Story setup</span></button>
    <button className="icon-button" aria-label="Toggle context" aria-pressed={context} disabled={!onContext} onClick={onContext}><PanelRight size={18} /><span className="action-label">Context</span></button>
    <button className="icon-button" aria-label="Open collaborator" aria-pressed={side} disabled={!onSide} onClick={onSide}><MessageSquareText size={18} /><span className="action-label">Collaborator</span></button>
  </>
  return <header className="chat-heading"><div><span className="eyebrow">{branchName}{curation?.archived ? ' · Archived' : ''}</span><h1>{story.title}</h1></div><div className="header-actions">
    <button className="button quiet" aria-label={`Branches (${story.branches.length})`} onClick={onMap}><GitBranch size={16} /><span>Branches</span><small>{story.branches.length}</small></button>
    <div className="workspace-actions-inline">{actions}</div>
    <details className="workspace-actions-menu" onClick={event => { if ((event.target as Element).closest('button')) event.currentTarget.open = false }}><summary aria-label="Workspace tools">Tools</summary><div>{actions}</div></details>
  </div></header>
}
