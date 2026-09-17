/** Decorative emblem; the surrounding link or heading supplies its accessible name. */
export function StudyMark({ size = 40 }: { size?: number }) {
  return <img className="study-mark" src="/brand/study-mark.svg" alt="" aria-hidden="true" width={size} height={size} draggable={false} />
}
