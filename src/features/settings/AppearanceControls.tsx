import { useState, type CSSProperties } from 'react'
import { interfaceScale, type Appearance } from './appearance'
import { defaultPalette, paletteReadability, paletteStyles, validHex, validPalette, type Palette } from './palette'

export function InterfaceScale({ appearance, onChange }: { appearance: Appearance; onChange: (value: number) => void }) {
  const scale = interfaceScale(appearance)
  return <div className="form-stack"><label className="field"><span>Interface size <small>{scale}%</small></span><input aria-label="Interface size" type="range" min="85" max="200" step="1" value={scale} onChange={event => onChange(Number(event.target.value))} /></label>
    <label className="field"><span>Exact interface size (%)</span><input key={scale} type="number" min="85" max="200" step="any" defaultValue={scale} onBlur={event => { const n = Number(event.target.value); if (event.target.value && Number.isFinite(n)) onChange(Math.max(85, Math.min(200, n))); else event.target.value = String(scale) }} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }} /></label>
    <div className="size-presets">{[100, 125, 150, 175, 200].map(value => <button className="button" aria-pressed={scale === value} key={value} onClick={() => onChange(value)}>{value}%</button>)}</div><button className="text-button" onClick={() => onChange(100)}>Reset interface size to 100%</button></div>
}

export function CustomPalette({ appearance, onChange }: { appearance: Appearance; onChange: (value: Partial<Appearance>) => void }) {
  const [draft, setDraft] = useState<Palette>(validPalette(appearance.customPalette) ? appearance.customPalette : defaultPalette)
  const readability = paletteReadability(draft)
  const update = (key: keyof Palette, value: string) => setDraft({ ...draft, [key]: value })
  return <details className="custom-palette"><summary>Custom palette</summary><div className="form-stack">
    {(['accent', 'background', 'surface', 'text'] as const).map(key => <div className="color-control" key={key}><label><span>{key}</span><input aria-label={`${key} color`} type="color" value={validHex(draft[key]) ? draft[key] : defaultPalette[key]} onChange={event => update(key, event.target.value)} /></label><label className="field"><span>{key} hex</span><input spellCheck={false} value={draft[key]} onChange={event => update(key, event.target.value)} aria-invalid={!validHex(draft[key])} maxLength={7} /></label></div>)}
    <div className="palette-preview" style={paletteStyles(validPalette(draft) ? draft : defaultPalette) as CSSProperties}><p className="prose">There was still a little light at the end of the hall.</p><button className="button primary">Sample action</button><label className="check-row"><input type="checkbox" defaultChecked />Selected option</label><p className="subtle">Supporting text and visible focus</p><p className="error-notice">! A sample error message</p></div>
    <p role="status" className="subtle">{validPalette(draft) ? `Text contrast ${readability.text.toFixed(2)}:1 (needs 4.5); accent contrast ${readability.accent.toFixed(2)}:1 (needs 3).` : 'Use six-digit hex colors, for example #c5a46d.'}{!readability.valid && ' Adjust the palette before applying.'}</p>
    <button className="button primary" disabled={!readability.valid} onClick={() => onChange({ theme: 'custom', customPalette: { ...draft } })}>Apply custom palette</button><button className="text-button" onClick={() => onChange({ theme: 'ink' })}>Reset to Ink preset</button>
  </div></details>
}
