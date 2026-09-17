import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  description: string
  children: ReactNode
  wide?: boolean
  focusOnClose?: () => HTMLElement | null
}

export function Modal({ open, onClose, title, description, children, wide = false, focusOnClose }: Props) {
  const [returnFocus] = useState(() => document.activeElement as HTMLElement | null)
  return <Dialog.Root open={open} onOpenChange={(next) => { if (!next) onClose() }}>
    <Dialog.Portal>
      <Dialog.Overlay className="dialog-overlay" />
      <Dialog.Content className={`dialog-content ${wide ? 'dialog-wide' : ''}`} onEscapeKeyDown={event => { if (event.target instanceof Element && event.target.closest('[role="combobox"][aria-expanded="true"]')) event.preventDefault() }} onCloseAutoFocus={(event) => { event.preventDefault(); (focusOnClose?.() ?? returnFocus)?.focus() }}>
        <header className="dialog-header">
          <div><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description}</Dialog.Description></div>
          <Dialog.Close className="icon-button" aria-label="Close dialog"><X /></Dialog.Close>
        </header>
        {children}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
