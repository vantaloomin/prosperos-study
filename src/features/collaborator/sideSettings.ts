import type { CompanionWork } from './workTypes'
export interface SideSettings { profiles: string[]; compare: boolean; paths: string[]; disclosure: string; reads: number; work?: CompanionWork }
export const defaultSideSettings: SideSettings = { profiles: [], compare: false, paths: [], disclosure: 'spoiler-conscious', reads: 3 }
