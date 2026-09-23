import { useEffect } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { useToastStore, type ToastItem, type ToastVariant } from '@/lib/store/useToastStore'

const VARIANT_BORDER: Record<ToastVariant, string> = {
  error: 'border-l-4 border-l-danger border-border/80',
  success: 'border-l-4 border-l-success border-border/80',
  info: 'border-l-4 border-l-accent border-border/80',
}

const VARIANT_ICON = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
}

const VARIANT_ICON_COLOR: Record<ToastVariant, string> = {
  error: 'text-danger',
  success: 'text-success',
  info: 'text-accent',
}

// Error toasts stay until dismissed — they can carry information the user needs after
// looking away (e.g. a generation failure). Success/info are transient nudges.
const AUTO_DISMISS_MS: Record<ToastVariant, number | null> = {
  error: null,
  success: 3500,
  info: 4500,
}

function Toast({ id, message, variant }: ToastItem) {
  const dismiss = useToastStore((s) => s.dismiss)
  const Icon = VARIANT_ICON[variant]

  useEffect(() => {
    const duration = AUTO_DISMISS_MS[variant]
    if (duration === null) return
    const t = setTimeout(() => dismiss(id), duration)
    return () => clearTimeout(t)
  }, [id, variant, dismiss])

  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={`animate-toast-in pointer-events-auto flex items-start gap-3 rounded-lg border bg-bg-elevated/95 p-3.5 text-xs text-text shadow-2xl backdrop-blur-md transition-all ${VARIANT_BORDER[variant]}`}
    >
      <Icon size={16} strokeWidth={2} className={`mt-0.5 shrink-0 ${VARIANT_ICON_COLOR[variant]}`} />
      <span className="flex-1 leading-relaxed whitespace-pre-wrap">{message}</span>
      <button
        onClick={() => dismiss(id)}
        aria-label="Dismiss notification"
        className="shrink-0 text-text-muted transition-colors hover:text-text"
      >
        <X size={14} strokeWidth={2} />
      </button>
    </div>
  )
}

export function ToastViewport() {
  const toasts = useToastStore((s) => s.toasts)
  if (toasts.length === 0) return null
  return (
    <div
      id="toast-container"
      className="pointer-events-none fixed top-5 right-6 z-[99999] flex w-full max-w-sm flex-col gap-2.5"
    >
      {toasts.map((t) => (
        <Toast key={t.id} {...t} />
      ))}
    </div>
  )
}
