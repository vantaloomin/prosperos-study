import type { Deck, DeckCard } from './types'

export interface EditableCard extends Omit<DeckCard, 'weight' | 'tags'> { weight: string; tags: string }
export interface DeckDraft { name: string; description: string; note: string; unsupported: Record<string, unknown>; cards: EditableCard[] }
export const blankCard = (): EditableCard => ({ id: crypto.randomUUID(), title: '', text: '', tags: '', weight: '1', enabled: true })
export const deckDraft = (deck?: Deck): DeckDraft => ({ name: deck?.name ?? '', description: deck?.description ?? '', note: '', unsupported: deck?.unsupported ?? {}, cards: deck ? deck.content.cards.map(card => ({ ...card, weight: String(card.weight), tags: card.tags.join(', ') })) : [blankCard()] })
