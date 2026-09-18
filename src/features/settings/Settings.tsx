import { Check, Monitor, Moon } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Models } from '../models/Models'
import { Prompts } from '../prompts/Prompts'
import { readingFonts, interfaceFonts, type Appearance } from './appearance'
import type { Selection } from '../../types'
import { Loading } from '../../components/Feedback'
import { CustomPalette, InterfaceScale } from './AppearanceControls'

const Archives = lazy(() => import('../export/Archives').then((module) => ({ default: module.Archives })))

export function Settings({ appearance, onChange, selection, onOpen }: { appearance: Appearance; onChange: (next: Appearance) => void; selection: Selection; onOpen: (selection: Selection) => void }) {
  const [tab, setTab] = useState('models')
  return <main className="page settings-page" data-panel={tab}><header className="page-heading"><div><span className="eyebrow">MAKE YOURSELF AT HOME</span><h1>Settings</h1><p>Your study, made to fit you.</p></div></header><div className="tabs settings-tabs">{['models', 'prompts', 'appearance', 'backups'].map((item) => <button key={item} aria-pressed={tab === item} onClick={() => setTab(item)}>{item}</button>)}</div>
    {tab === 'models' && <Models />}{tab === 'prompts' && <Prompts />}{tab === 'appearance' && <AppearanceSettings appearance={appearance} onChange={onChange} />}
    {tab === 'backups' && <Suspense fallback={<Loading label="Opening backups…" />}><Archives selection={selection} onOpen={onOpen} /></Suspense>}
  </main>
}

function AppearanceSettings({ appearance, onChange }: { appearance: Appearance; onChange: (next: Appearance) => void }) {
  const patch = (change: Partial<Appearance>) => onChange({ ...appearance, ...change })
  return <>
    <section className="settings-section"><div><Moon size={20} /><h2>Reading & appearance</h2><p>Changes apply immediately and stay on this device.</p></div><div className="settings-controls"><span className="field-label">Palette</span><div className="palette-options">{['ink', 'slate', 'umber', 'moss', 'wine', 'ash'].map((theme) => <button key={theme} data-palette={theme} className={`palette ${theme === appearance.theme ? 'selected' : ''}`} onClick={() => patch({ theme })} aria-pressed={theme === appearance.theme}><span />{theme}{theme === appearance.theme && <Check size={14} />}</button>)}</div>
      <CustomPalette appearance={appearance} onChange={patch} /><div className="typography-controls"><h3>Interface</h3><label className="field"><span>Interface font</span><select value={appearance.interfaceFont ?? 'ibm-plex'} onChange={e => patch({ interfaceFont: e.target.value })}>{interfaceFonts.map(font => <option key={font.id} value={font.id}>{font.name} — {font.description}</option>)}</select><small>Menus, buttons, labels, and headings. Reading preferences stay independent.</small></label><InterfaceScale appearance={appearance} onChange={interfaceScale => patch({ interfaceScale })} /><div className="interface-preview"><strong>Your writing room</strong><p>Characters, Canon, and every possible next page.</p><button className="button" type="button">A sample button</button></div></div>
      <div className="typography-controls"><h3>Reading</h3><label className="field"><span>Reading font</span><select value={appearance.font ?? 'literata'} onChange={e => patch({ font: e.target.value })}>{readingFonts.map(font => <option key={font.id} value={font.id}>{font.name} — {font.description}</option>)}</select><small>Applies to prose and the writing composer. Fonts are served locally; choose whichever feels comfortable to read.</small></label>
      <label className="field"><span>Reading size <small>{appearance.fontSize}px</small></span><input aria-label="Reading size" type="range" min="15" max="28" value={appearance.fontSize} onChange={(e) => patch({ fontSize: Number(e.target.value) })} /></label>
      <div className="prose reading-preview">The door stood open. Beyond it, there was still a little light.</div></div>
    </div></section>
    <section className="settings-section"><div><Monitor size={20} /><h2>Motion</h2><p>Your operating system's reduced-motion preference is always respected.</p></div><label className="check-row"><input type="checkbox" checked={appearance.reducedMotion} onChange={(e) => patch({ reducedMotion: e.target.checked })} /><span>Always reduce motion<small>Keep feedback while removing spatial transitions.</small></span></label></section>
  </>
}
