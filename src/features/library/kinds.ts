import type { AssetKind } from '../../types'

// Legacy archive identities stay intact; they share the Character experience.
export const libraryKind = (kind: AssetKind): 'character' | 'lorebook' => kind === 'persona' ? 'character' : kind
export const assetLabel = (kind: AssetKind): string => kind === 'lorebook' ? 'Canon collection' : 'Character'
