import { ChevronDown, Check } from 'lucide-react'
import { useEffect, useLayoutEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { DiscoveredModel } from './discovery'
import { filterModels } from './modelFilter'

export function ModelCombobox({ models, value, onChange }: { models: DiscoveredModel[]; value: string; onChange: (id: string) => void }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const list = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const popup = useRef<HTMLDivElement>(null)
  const filtered = useMemo(() => filterModels(models, query), [models, query])
  const selected = models.find(model => model.id === value)
  const choose = (model: DiscoveredModel) => { onChange(model.id); setOpen(false); setQuery(''); input.current?.focus() }
  useEffect(() => { if (open) scrollActiveOption(list.current, active) }, [active, open, filtered])
  useLayoutEffect(() => { if (open) { input.current?.scrollIntoView({ block: 'nearest' }); positionPopup(input.current, popup.current, list.current) } }, [open, filtered])
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); setQuery(''); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setOpen(true)
      setActive(index => Math.max(0, Math.min(filtered.length - 1, open ? index + (event.key === 'ArrowDown' ? 1 : -1) : 0)))
    }
    if (event.key === 'Enter' && open) { event.preventDefault(); if (filtered[active]) choose(filtered[active]) }
  }
  return <div className="model-combobox" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setQuery('') } }}>
    <label htmlFor={id}>Available models <small>{models.length} returned</small></label>
    <div className="model-search-input"><input ref={input} id={id} role="combobox" autoComplete="off" aria-expanded={open} aria-controls={`${id}-list`} aria-autocomplete="list" aria-activedescendant={open && filtered[active] ? `${id}-${active}` : undefined} value={open ? query : selected?.name ?? ''} placeholder="Type to filter models…" onClick={() => setOpen(true)} onFocus={() => { setOpen(true); setActive(0) }} onChange={event => { setQuery(event.target.value); setOpen(true); setActive(0) }} onKeyDown={keyDown} /><button type="button" tabIndex={-1} aria-label="Show available models" onMouseDown={event => event.preventDefault()} onClick={() => { input.current?.focus(); setOpen(!open) }}><ChevronDown size={16} /></button></div>
    {open && <div ref={popup} className="model-search-popup"><p role="status">{filtered.length} of {models.length} models</p><div ref={list} id={`${id}-list`} role="listbox" aria-label="Available models">{filtered.map((model, index) => <div key={model.id} id={`${id}-${index}`} role="option" aria-selected={model.id === value} data-active={index === active} onMouseDown={event => event.preventDefault()} onMouseMove={() => setActive(index)} onClick={() => choose(model)}><span>{model.name}{model.name !== model.id && <small>{model.id}</small>}</span>{model.id === value && <Check size={15} />}</div>)}</div>{!filtered.length && <p>No matching models. Try another name or enter a Model ID below.</p>}</div>}
  </div>
}

function positionPopup(input: HTMLInputElement | null, popup: HTMLDivElement | null, list: HTMLDivElement | null) {
  if (!input || !popup || !list) return
  const bounds = input.closest('.dialog-body')?.getBoundingClientRect() ?? { top: 0, bottom: innerHeight }
  const field = input.getBoundingClientRect()
  const below = bounds.bottom - field.bottom - 12
  const above = field.top - bounds.top - 12
  const up = below < 230 && above > below
  popup.dataset.side = up ? 'above' : 'below'
  list.style.maxHeight = `${Math.max(70, Math.min(230, (up ? above : below) - 44))}px`
}

function scrollActiveOption(list: HTMLDivElement | null, index: number) {
  const option = list?.children[index]
  if (!list || !option) return
  const box = list.getBoundingClientRect()
  const item = option.getBoundingClientRect()
  if (item.top < box.top) list.scrollTop -= box.top - item.top
  if (item.bottom > box.bottom) list.scrollTop += item.bottom - box.bottom
}
