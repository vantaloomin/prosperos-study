import type { LoreReceipt } from '../library/LoreReceiptView'

export interface TableRow {
  id: string; low: number; high: number; label: string; instruction: string
  kind: 'event' | 'no_event' | 'progress'; child: string | null; major: boolean; tags: string[]
}
export interface OverflowResult { id: string; label: string; instruction: string; child: string | null; domain_move: number }
export interface TableDefinition {
  id: string; name: string; purpose: 'event' | 'handling' | 'carrier' | 'extra' | 'texture'
  die: number; rows: TableRow[]; note: string
  low_overflow: OverflowResult | null; high_overflow: OverflowResult | null
}
export interface TableVersion { id: string; table_id: string; number: number; definition: TableDefinition; hash: string; created_at: string }
export interface RngSettings {
  automatic_assessment?: boolean
  enabled: boolean; narrative_push: boolean; encounter: boolean; handling: boolean
  proficiency: boolean; fracture: boolean; preparation: boolean; subresults: boolean
  carriers: boolean; textures: boolean; pressure_cap: boolean; domain_progression: boolean
  chance: number; cooldown: number; major_limit: number
  enabled_extras: string[]; disabled_tables: string[]; excluded_rows: Record<string, string[]>
  table_versions: Record<string, string>; texture_tables: Record<string, string>
}
export interface MechanicState {
  scene: number; beat: number; cooldown: number | null; major_events: number; unresolved_event: boolean
  handling_history: number[]; domains: Record<string, number>; last_opportunity_id: string | null
}
export interface MechanicsBrief {
  automatic_assessment?: boolean; assessment?: { id: string; generation_id: string | null } | null
  enabled: boolean; state: MechanicState
  pending: { id: string; label: string; manual: boolean; stale: boolean } | null
}
export interface MechanicsContext extends MechanicsBrief {
  story_revision: number; settings: RngSettings; tables: TableVersion[]
  odds: Record<string, { id: string; enabled: boolean; percent: number }[]>
  history: { id: string; branch_id: string; created_at: string }[]
}
export interface Attempt { action: string; actor: string; domain: string; level: number; fractured: boolean; prepared: boolean }
export interface Beat {
  label: string; completed: boolean; waiting_for_player: boolean; protected: boolean
  resolves_event: boolean; new_scene: boolean; family: 'narrative-push' | 'encounter' | 'none'
  attempt: Attempt | null; extras: string[]
}
export interface Outcome { status?: string; reason?: string; chain?: { table_id: string; face: number; row: TableRow }[]; band?: { label: string; instruction: string } }
export interface Opportunity {
  id: string; branch_id: string; created_at: string
  snapshot: {
    lore?: LoreReceipt
    beat: Beat; manual: boolean; seed: string; algorithm: string; eligibility: string | null
    before: MechanicState; after: MechanicState; settings: RngSettings
    event: Outcome; handling: Outcome; extras: Record<string, Outcome>
    writer: Record<string, unknown>; draws: { stream: string; counter: number; purpose: string; sides: number; result: number }[]
    tables: Record<string, TableVersion>; reroll_of: string | null
  }
}
