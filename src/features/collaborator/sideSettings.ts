export interface SideSettings { profiles: string[]; compare: boolean; paths: string[]; disclosure: string; reads: number }
export const defaultSideSettings: SideSettings = { profiles: [], compare: false, paths: [], disclosure: 'spoiler-conscious', reads: 3 }
