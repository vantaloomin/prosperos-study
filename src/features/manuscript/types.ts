export interface SceneSelection { id: string; title: string; branch_id: string; head_id: string; from_node_id: string; through_node_id: string }
export interface Chapter { id: string; title: string; scenes: SceneSelection[] }
export interface Bookmark { id: string; scene_id: string; node_id: string; label: string }
export interface BookDocument { title: string; author: string; language: string; include_contributions: boolean; scene_headings: boolean; chapters: Chapter[]; bookmarks: Bookmark[] }
export interface Manuscript { id: string | null; story_id: string; revision: number; document: BookDocument }
export interface BookScene { id: string; title: string; branch_id: string; telling: string; changed: boolean; words: number; passages: { node_id: string; text: string }[] }
export interface Publication { title: string; author: string; language: string; scene_headings: boolean; words: number; revision: number; chapters: { id: string; title: string; scenes: BookScene[] }[] }
export interface ReadingTarget { sceneId: string; nodeId?: string }

export function moveItem<T>(items: T[], index: number, direction: number): T[] {
  const destination = index + direction
  if (destination < 0 || destination >= items.length) return items
  const result = [...items]
  const [item] = result.splice(index, 1)
  result.splice(destination, 0, item)
  return result
}

export function removeScene(document: BookDocument, sceneId: string): BookDocument {
  return { ...document, chapters: document.chapters.map(chapter => ({ ...chapter, scenes: chapter.scenes.filter(scene => scene.id !== sceneId) })), bookmarks: document.bookmarks.filter(mark => mark.scene_id !== sceneId) }
}
