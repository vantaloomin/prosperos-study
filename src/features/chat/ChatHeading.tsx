import { Feather, GitBranch, ListChecks, MessageSquareText, PanelRight, SlidersHorizontal } from 'lucide-react'
import type { Story } from '../../types'

interface Props {
  story: Story
  branchName: string
  context?: boolean
  side?: boolean
  tools?: boolean
  onTools?: () => void
  onMap: () => void
  onWorkflow?: () => void
  onDetails?: () => void
  onContext?: () => void
  onSide?: () => void
}

export function ChatHeading({ story, branchName, context = false, side = false, tools = false, onTools, onMap, onWorkflow, onDetails, onContext, onSide }: Props) {
  return <header className="chat-heading"><div><span className="eyebrow">{branchName}</span><h1>{story.title}</h1></div><div className="header-actions">
    <button className="button quiet" aria-label={`Branches (${story.branches.length})`} onClick={onMap}><GitBranch size={16} /><span>Branches</span><small>{story.branches.length}</small></button>
    <button className="icon-button" aria-label="Writing tools" title="Writing tools" aria-pressed={tools} onClick={onTools}><Feather size={18} /></button>
    <button className="icon-button" aria-label="Story workflow" title="Story workflow" disabled={!onWorkflow} onClick={onWorkflow}><ListChecks size={18} /></button>
    <button className="icon-button" aria-label="Story details" disabled={!onDetails} onClick={onDetails}><SlidersHorizontal size={18} /></button>
    <button className="icon-button" aria-label="Toggle context" aria-pressed={context} disabled={!onContext} onClick={onContext}><PanelRight size={18} /></button>
    <button className="icon-button" aria-label="Open collaborator" aria-pressed={side} disabled={!onSide} onClick={onSide}><MessageSquareText size={18} /></button>
  </div></header>
}
