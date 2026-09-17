import { AlertCircle, LoaderCircle } from 'lucide-react'

export function ErrorNotice({ message }: { message?: string }) {
  if (!message) return null
  return <p role="alert" className="error-notice"><AlertCircle size={16} /><span>{message}</span></p>
}

export function Loading({ label = 'Opening your workspace…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle size={20} />{label}</div>
}

export function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="empty"><span className="eyebrow">A little room for possibility</span><h2>{title}</h2>{children}</div>
}
