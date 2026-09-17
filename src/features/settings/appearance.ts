export interface Appearance { reducedMotion: boolean; fontSize: number; theme: string; font?: string; interfaceFont?: string; interfaceSize?: number }
export const defaultAppearance: Appearance = { reducedMotion: false, fontSize: 17, theme: 'ink', font: 'literata', interfaceFont: 'ibm-plex', interfaceSize: 16 }
export const readingFonts = [
  { id: 'literata', name: 'Literata', description: 'The original · contemporary book serif', family: "'Literata', Georgia, serif" },
  { id: 'arimo', name: 'Arimo', description: 'Clean sans serif · familiar Arial proportions', family: "'Arimo', Arial, sans-serif" },
  { id: 'opendyslexic', name: 'OpenDyslexic', description: 'Distinctive, weighted letterforms', family: "'OpenDyslexic', Arial, sans-serif" },
  { id: 'atkinson', name: 'Atkinson Hyperlegible', description: 'Clear, distinctive characters', family: "'Atkinson Hyperlegible', Arial, sans-serif" },
  { id: 'lora', name: 'Lora', description: 'Warm serif with a calligraphic touch', family: "'Lora', Georgia, serif" },
  { id: 'source-serif', name: 'Source Serif 4', description: 'An editorial serif for long passages', family: "'Source Serif 4', Georgia, serif" },
] as const

export function readingFont(id?: string): string {
  return (readingFonts.find(font => font.id === id) ?? readingFonts[0]).family
}

export const interfaceFonts = [
  { id: 'ibm-plex', name: 'IBM Plex Sans', description: 'The original interface font', family: "'IBM Plex Sans', sans-serif" },
  ...readingFonts,
]
export function interfaceFont(id?: string): string {
  return (interfaceFonts.find(font => font.id === id) ?? interfaceFonts[0]).family
}
export function appearanceStyles(appearance: Appearance) {
  return {
    '--prose-size': `${appearance.fontSize}px`, '--prose-font': readingFont(appearance.font),
    '--interface-font': interfaceFont(appearance.interfaceFont),
    '--interface-heading-font': !appearance.interfaceFont || appearance.interfaceFont === 'ibm-plex' ? readingFont('literata') : interfaceFont(appearance.interfaceFont),
    '--interface-size': `${Math.max(14, Math.min(20, appearance.interfaceSize ?? 16))}px`,
  }
}
