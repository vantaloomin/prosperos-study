import { useCallback, useImperativeHandle, useLayoutEffect, useRef, useState, type Ref } from 'react'
import type { PassageReader } from './passageNavigation'
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso'
import type { Branch } from '../../types'
import { messageLabels, type StoryMode } from '../stories/storyMode'
import { MessageCard } from './MessageCard'
import { loadPosition } from './readingPosition'
import { hasReadingAnchor, initialMessageIndex, passagePosition } from './transcriptWindow'
import { VirtualReadingPosition } from './VirtualReadingPosition'
import { PassageFinder } from './PassageFinder'
import { WritingSurface } from '../generation/WritingSurface'
import '../../styles/transcript-window.css'

function ChapterMark() { return <div className="reading-column windowed-mark"><div className="chapter-mark"><span />A beginning, and what followed<span /></div></div> }
function EndMark() { return <div className="reading-column windowed-mark"><WritingSurface after={null} /><div className="end-mark">· · ·</div></div> }
const components = { Header: ChapterMark, Footer: EndMark }

export function WindowedTranscript({ branch, mode, onBranch, reader }: { branch: Branch; mode: StoryMode; onBranch: (id: string) => void; reader: Ref<PassageReader> }) {
  const labels = messageLabels(mode)
  const virtuoso = useRef<VirtuosoHandle>(null)
  const reading = useRef<VirtualReadingPosition | null>(null)
  const viewport = useRef<HTMLElement | null>(null)
  const [finder, setFinder] = useState(false)
  const [initial] = useState(() => ({ position: loadPosition(branch.id), messages: branch.messages }))
  const last = branch.messages.at(-1)!.id
  const scroller = useCallback((element: HTMLElement | Window | null) => {
    reading.current?.dispose()
    viewport.current = element instanceof HTMLElement ? element : null
    const mount = (position: ReturnType<typeof loadPosition>) => virtuoso.current?.scrollToIndex({ index: initialMessageIndex(branch.messages, position), align: position?.atEnd === false ? 'start' : 'end', behavior: 'auto' })
    reading.current = element instanceof HTMLElement ? new VirtualReadingPosition(element, branch.id, last, (block) => hasReadingAnchor(branch.messages, block), mount) : null
  }, [branch.id, branch.messages, last])
  useLayoutEffect(() => () => reading.current?.dispose(), [])
  const go = (index: number) => {
    reading.current?.seek(passagePosition(branch.messages[index].id), last)
    virtuoso.current?.scrollToIndex({ index, align: 'start', behavior: 'auto' })
    setFinder(false)
  }
  useImperativeHandle(reader, () => ({ branchId: branch.id, show: (messageId) => {
    const index = branch.messages.findIndex((message) => message.id === messageId)
    if (index < 0) return false
    reading.current?.seek(passagePosition(messageId), last)
    virtuoso.current?.scrollToIndex({ index, align: 'start', behavior: 'auto' })
    viewport.current?.focus({ preventScroll: true })
    return true
  } }), [branch.id, branch.messages, last])
  const latest = () => {
    reading.current?.seek(null, last)
    virtuoso.current?.scrollToIndex({ index: branch.messages.length - 1, align: 'end', behavior: 'auto' })
  }
  return <div className="transcript-window"><div className="transcript-tools"><span>{branch.messages.length.toLocaleString()} contributions</span><button className="text-button" onClick={() => go(0)}>First</button><button className="text-button" onClick={latest}>Latest</button><button className="text-button" onClick={() => setFinder(true)}>Find a passage</button></div>
    <Virtuoso ref={virtuoso} className="transcript virtual-transcript" tabIndex={0} role="region" aria-label="Story history" data-transcript-ready="false"
      data={branch.messages} computeItemKey={(_, message) => message.id} scrollerRef={scroller} components={components}
      defaultItemHeight={300} increaseViewportBy={{ top: 700, bottom: 700 }} atBottomThreshold={80}
      initialTopMostItemIndex={{ index: initialMessageIndex(initial.messages, initial.position), align: initial.position?.atEnd === false ? 'start' : 'end' }}
      totalListHeightChanged={() => reading.current?.refresh()}
      itemContent={(index, message) => <div className="reading-column windowed-message" data-message-index={index}><MessageCard message={message} label={labels[message.role]} position={`Contribution ${index + 1} of ${branch.messages.length}`} branch={branch} onBranch={onBranch} /><WritingSurface after={message.id} /></div>} />
    {finder && <PassageFinder messages={branch.messages} onClose={() => setFinder(false)} onSelect={go} />}
  </div>
}
