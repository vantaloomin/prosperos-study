export interface Palette { accent: string; background: string; surface: string; text: string }
export const defaultPalette: Palette = { accent: '#c5a46d', background: '#191816', surface: '#201f1c', text: '#ede5d6' }
export const validHex = (value: unknown): value is string => typeof value === 'string' && /^#[\da-f]{6}$/i.test(value)
export function validPalette(value: unknown): value is Palette {
  if (!value || typeof value !== 'object') return false
  return (['accent', 'background', 'surface', 'text'] as const).every(key => validHex((value as Palette)[key]))
}
const channels = (hex: string) => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16))

function luminance(hex: string) {
  const rgb = channels(hex).map(value => { const s = value / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 })
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722
}
export function contrast(left: string, right: string) {
  const a = luminance(left), b = luminance(right)
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
}
function mix(left: string, right: string, weight: number) {
  const second = channels(right)
  return '#' + channels(left).map((value, index) => Math.round(value * (1 - weight) + second[index] * weight).toString(16).padStart(2, '0')).join('')
}
const inkOn = (color: string) => contrast(color, '#ffffff') > contrast(color, '#000000') ? '#ffffff' : '#000000'
function readableMix(background: string, text: string, minimum: number) {
  for (const weight of [.6, .75, .9, 1]) {
    const mixed = mix(background, text, weight)
    if (contrast(background, mixed) >= minimum) return mixed
  }
  return text
}
export function paletteReadability(value: Palette) {
  if (!validPalette(value)) return { valid: false, text: 0, accent: 0 }
  const text = Math.min(contrast(value.text, value.background), contrast(value.text, value.surface))
  const accent = Math.min(contrast(value.accent, value.background), contrast(value.accent, value.surface))
  return { valid: text >= 4.5 && accent >= 3, text, accent }
}
export function paletteStyles(palette?: Palette) {
  const p = palette && validPalette(palette) ? palette : defaultPalette
  return {
    '--canvas': p.background, '--surface': p.surface, '--text': p.text, '--accent': p.accent,
    '--raised': mix(p.surface, p.text, .06), '--border': readableMix(p.surface, p.text, 3),
    '--muted': readableMix(p.surface, p.text, 4.5), '--faint': readableMix(p.surface, p.text, 4.5),
    '--accent-hover': mix(p.accent, inkOn(p.accent), .1), '--accent-tint': mix(p.surface, p.accent, .15),
    '--accent-border': p.accent, '--accent-subtle': mix(p.surface, p.accent, .5), '--on-accent': inkOn(p.accent),
    '--selection': mix(p.background, p.accent, .35), '--danger-text': readableMix(p.surface, p.text, 4.5),
    colorScheme: luminance(p.background) > .45 ? 'light' : 'dark',
  }
}
