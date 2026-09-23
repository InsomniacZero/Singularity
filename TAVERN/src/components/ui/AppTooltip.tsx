import { useEffect, useRef, useState } from 'react'

/**
 * Custom Floating Tooltip (Exact janitorai-stats-tracker pattern)
 * Safe and lightweight - never mutates React DOM outside of user pointer interaction.
 */
export function AppTooltip() {
  const [text, setText] = useState<string>('')
  const [visible, setVisible] = useState(false)
  const [coords, setCoords] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const tooltipRef = useRef<HTMLDivElement>(null)
  const activeElementRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const positionTooltip = (el: HTMLElement) => {
      const tooltip = tooltipRef.current
      if (!tooltip) return

      const rect = el.getBoundingClientRect()
      const tooltipRect = tooltip.getBoundingClientRect()

      let top = rect.top - tooltipRect.height - 8
      let left = rect.left + rect.width / 2 - tooltipRect.width / 2

      if (top < 8) {
        top = rect.bottom + 8
      }

      const pad = 12
      if (left < pad) left = pad
      if (left + tooltipRect.width > window.innerWidth - pad) {
        left = window.innerWidth - pad - tooltipRect.width
      }

      setCoords({ x: Math.round(left), y: Math.round(top) })
    }

    const showTooltip = (el: HTMLElement) => {
      // If element has title, transfer to data-tooltip during hover to silence Chrome popup
      if (el.hasAttribute('title')) {
        const val = el.getAttribute('title')
        if (val) {
          el.setAttribute('data-tooltip', val)
          el.removeAttribute('title')
        }
      }

      const tooltipText = el.getAttribute('data-tooltip')
      if (!tooltipText || !tooltipText.trim()) return

      activeElementRef.current = el
      setText(tooltipText.trim())
      setVisible(true)

      requestAnimationFrame(() => {
        positionTooltip(el)
      })
    }

    const hideTooltip = () => {
      setVisible(false)
      activeElementRef.current = null
    }

    const handlePointerOver = (e: PointerEvent) => {
      const target = (e.target as HTMLElement | null)?.closest<HTMLElement>('[data-tooltip], [title]')
      if (target) {
        showTooltip(target)
      }
    }

    const handlePointerOut = (e: PointerEvent) => {
      const target = (e.target as HTMLElement | null)?.closest<HTMLElement>('[data-tooltip], [title]')
      if (target && target === activeElementRef.current) {
        hideTooltip()
      }
    }

    const handleFocusIn = (e: FocusEvent) => {
      const target = (e.target as HTMLElement | null)?.closest<HTMLElement>('[data-tooltip], [title]')
      if (target) {
        showTooltip(target)
      }
    }

    const handleFocusOut = () => {
      hideTooltip()
    }

    const handleActionClick = () => {
      hideTooltip()
    }

    const handleScroll = () => {
      hideTooltip()
    }

    document.body.addEventListener('pointerover', handlePointerOver, { passive: true })
    document.body.addEventListener('pointerout', handlePointerOut, { passive: true })
    document.body.addEventListener('focusin', handleFocusIn, { passive: true })
    document.body.addEventListener('focusout', handleFocusOut, { passive: true })
    document.body.addEventListener('click', handleActionClick, { passive: true })
    window.addEventListener('scroll', handleScroll, { passive: true })

    return () => {
      document.body.removeEventListener('pointerover', handlePointerOver)
      document.body.removeEventListener('pointerout', handlePointerOut)
      document.body.removeEventListener('focusin', handleFocusIn)
      document.body.removeEventListener('focusout', handleFocusOut)
      document.body.removeEventListener('click', handleActionClick)
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  return (
    <div
      ref={tooltipRef}
      role="tooltip"
      aria-hidden={!visible}
      className={`pointer-events-none fixed left-0 top-0 z-[10000] max-w-[280px] break-words rounded-lg border border-[#45413a] bg-[#1e1c19]/95 px-2.5 py-1 text-[11px] font-medium leading-relaxed tracking-wide text-[#faf8f5] shadow-xl backdrop-blur-md transition-opacity duration-150 ${
        visible ? 'opacity-100' : 'opacity-0'
      }`}
      style={{
        transform: `translate3d(${coords.x}px, ${coords.y}px, 0)`,
      }}
    >
      {text}
    </div>
  )
}
