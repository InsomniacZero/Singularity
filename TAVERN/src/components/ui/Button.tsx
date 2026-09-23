import { forwardRef, type ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'

const variantClasses: Record<Variant, string> = {
  primary: 'bg-accent text-white font-semibold border border-transparent shadow-sm hover:brightness-105 active:scale-[0.98]',
  secondary: 'bg-bg-elevated text-text border border-border hover:bg-bg-sunken hover:border-border-medium active:scale-[0.98]',
  ghost: 'text-text-muted hover:text-text hover:bg-bg-sunken active:scale-[0.98]',
  danger: 'bg-danger/15 text-danger border border-danger/30 hover:bg-danger hover:text-white active:scale-[0.98]',
  outline: 'bg-transparent text-text border border-border hover:border-text-muted active:scale-[0.98]',
}

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }>(
  function Button({ variant = 'secondary', className = '', ...props }, ref) {
    return (
      <button
        ref={ref}
        // Structured geometric radii (8px - var(--radius-md)), never rounded-full.
        className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-150 select-none disabled:cursor-not-allowed disabled:opacity-40 sm:py-1.5 ${variantClasses[variant]} ${className}`}
        {...props}
      />
    )
  },
)
