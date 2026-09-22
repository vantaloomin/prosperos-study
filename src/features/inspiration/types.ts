export interface DeckCard { id: string; title: string; text: string; tags: string[]; weight: number; enabled: boolean }
export interface DeckContent { cards: DeckCard[] }
export interface Deck { id: string; deck_id: string; number: number; name: string; description: string; content: DeckContent; unsupported: Record<string, unknown>; note: string; archived: boolean; revision: number }
export interface DeckFilters { tags: string[]; excluded_ids: string[] }
export interface Eligibility { protocol: number; replacement: boolean; filters: DeckFilters; total_units: number; cards: { card_id: string; reason: string; units: number; probability: { numerator: number; denominator: number } }[] }
export interface DeckPreview { selection: Eligibility; results: { ticket: number; card: DeckCard }[]; seed: string; recorded: false }
export interface DeckDraw { id: string; version_id: string; branch_id: string | null; head_id: string | null; selection: Eligibility; ticket: number; card_id: string; created_at: string; card: DeckCard; deck_name: string; deck_number: number; deck_id: string }
export interface PackReport { id: string; name: string; description: string; source_sha256: string; compatibility: string; activation: string; dependencies: unknown[]; decks: { key: string; name: string; description: string; content: DeckContent; unsupported: Record<string, unknown>; duplicates: { id: string; deck_id: string; name: string; number: number }[] }[] }
export interface PackChoice { key: string; included: boolean; duplicate_action: 'skip' | 'new'; target_deck_id: string | null; expected_version_id: string | null }
export interface PackResult { versions: Deck[]; skipped: { key: string }[] }
export type PackDocument = Record<string, unknown>
export const splitTags = (text: string) => text.split(',').map(tag => tag.trim()).filter(Boolean)
export const drawText = (draw: DeckDraw) => `Inspiration from ${draw.deck_name} v${draw.deck_number} · ${draw.card.title}\n${draw.card.text}`
