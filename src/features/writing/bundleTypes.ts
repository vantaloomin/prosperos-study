export interface BundleResource { key: string; kind: 'style' | 'recipe'; name: string; description: string; content: Record<string, unknown>; unsupported: Record<string, unknown> }
export interface WritingBundle { format: string; version: number; root: string; resources: BundleResource[]; references: { key: string; kind: string; name: string }[]; omitted_samples: number }
export type BundleMappings = Record<string, string | null>
export interface MappingOption { id: string; name: string; number?: number; table_id?: string }
export interface BundleReport {
  fingerprint: string; root: string; resources: BundleResource[]
  dependencies: { key: string; kind: 'model' | 'style' | 'table'; name: string; table_id: string | null; mapped: boolean; selected_name?: string }[]
  options: Record<'model' | 'style' | 'table', MappingOption[]>
  errors: string[]; unsupported: { resource: string; fields: string[] }[]
  omitted_samples: number; can_import: boolean; activation: string
}
