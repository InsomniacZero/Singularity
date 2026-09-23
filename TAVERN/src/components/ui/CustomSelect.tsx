import React, { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, Check, Search } from 'lucide-react'

export interface SelectOption {
  value: string
  label: ReactNode
  disabled?: boolean
  group?: string
}

export interface CustomSelectProps {
  value?: string | number
  defaultValue?: string | number
  onChange?: (e: { target: { value: string } }) => void
  disabled?: boolean
  className?: string
  placeholder?: string
  options?: SelectOption[]
  children?: ReactNode
  id?: string
  name?: string
  'aria-label'?: string
}

function extractOptions(children?: ReactNode, directOptions?: SelectOption[]): SelectOption[] {
  if (directOptions && directOptions.length > 0) return directOptions
  const result: SelectOption[] = []

  const processNode = (node: ReactNode, currentGroup?: string) => {
    if (!node) return
    if (Array.isArray(node)) {
      node.forEach((n) => processNode(n, currentGroup))
      return
    }
    if (React.isValidElement(node)) {
      if (node.type === 'option') {
        result.push({
          value: String(node.props.value ?? ''),
          label: node.props.children ?? node.props.label ?? String(node.props.value ?? ''),
          disabled: !!node.props.disabled,
          group: currentGroup,
        })
      } else if (node.type === 'optgroup') {
        const groupLabel = node.props.label ? String(node.props.label) : undefined
        processNode(node.props.children, groupLabel)
      } else if (node.props?.children) {
        processNode(node.props.children, currentGroup)
      }
    }
  }

  processNode(children)
  return result
}

export function CustomSelect({
  value: controlledValue,
  defaultValue,
  onChange,
  disabled,
  className = '',
  placeholder = 'Select...',
  options: directOptions,
  children,
  id,
  name,
  'aria-label': ariaLabel,
}: CustomSelectProps) {
  const [internalValue, setInternalValue] = useState<string>(
    controlledValue !== undefined ? String(controlledValue) : defaultValue !== undefined ? String(defaultValue) : '',
  )
  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const activeValue = controlledValue !== undefined ? String(controlledValue) : internalValue
  const rawOptions = extractOptions(children, directOptions)
  const selectedOption = rawOptions.find((opt) => opt.value === activeValue)

  // Focus search input when popover opens
  useEffect(() => {
    if (isOpen && rawOptions.length > 5) {
      setTimeout(() => searchInputRef.current?.focus(), 50)
    }
    if (!isOpen) {
      setSearchQuery('')
    }
  }, [isOpen, rawOptions.length])

  useEffect(() => {
    if (!isOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const handleSelect = (val: string) => {
    if (controlledValue === undefined) {
      setInternalValue(val)
    }
    onChange?.({ target: { value: val } })
    setIsOpen(false)
  }

  const filteredOptions = useMemo(() => {
    if (!searchQuery.trim()) return rawOptions
    const q = searchQuery.toLowerCase().trim()
    return rawOptions.filter((opt) => {
      const labelStr = typeof opt.label === 'string' ? opt.label : String(opt.value)
      return labelStr.toLowerCase().includes(q) || (opt.group && opt.group.toLowerCase().includes(q))
    })
  }, [rawOptions, searchQuery])

  let lastGroup: string | undefined = undefined

  return (
    <div ref={containerRef} className={`relative inline-block w-full text-left ${className}`}>
      <button
        type="button"
        id={id}
        name={name}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        disabled={disabled}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm text-text outline-none transition-all duration-150 select-none ${
          isOpen
            ? 'border-accent bg-bg-elevated ring-1 ring-accent/30 shadow-sm'
            : 'border-border bg-bg-sunken hover:border-border-medium hover:bg-bg-elevated/80'
        } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
      >
        <span className="truncate text-left font-normal">
          {selectedOption ? selectedOption.label : <span className="text-text-muted">{placeholder}</span>}
        </span>
        <ChevronDown
          size={14}
          strokeWidth={2}
          className={`shrink-0 text-text-muted transition-transform duration-200 ${isOpen ? 'rotate-180 text-accent' : ''}`}
        />
      </button>

      {isOpen && (
        <div
          role="listbox"
          className="animate-in fade-in-0 zoom-in-95 absolute left-0 right-0 z-[100] mt-1.5 max-h-72 overflow-hidden rounded-lg border border-border-medium bg-bg-elevated p-1 shadow-2xl backdrop-blur-xl flex flex-col transition-all"
        >
          {rawOptions.length > 5 && (
            <div className="relative mb-1 border-b border-border/70 p-1.5">
              <Search size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter options…"
                className="w-full rounded-md bg-bg-sunken py-1.5 pl-7 pr-2.5 text-xs text-text outline-none ring-1 ring-border/50 placeholder:text-text-muted/60 focus:ring-accent/50"
              />
            </div>
          )}

          <div className="max-h-56 overflow-y-auto p-0.5 space-y-0.5">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-3 text-center text-xs text-text-muted">No matching options</div>
            ) : (
              filteredOptions.map((opt) => {
                const showGroupHeader = opt.group && opt.group !== lastGroup
                if (opt.group) lastGroup = opt.group
                const isSelected = opt.value === activeValue

                return (
                  <React.Fragment key={opt.value}>
                    {showGroupHeader && (
                      <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted/70">
                        {opt.group}
                      </div>
                    )}
                    <button
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      disabled={opt.disabled}
                      onClick={() => !opt.disabled && handleSelect(opt.value)}
                      className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs text-text transition-colors duration-100 ${
                        opt.disabled
                          ? 'cursor-not-allowed opacity-40'
                          : isSelected
                            ? 'bg-accent/15 font-medium text-accent'
                            : 'hover:bg-bg-sunken hover:text-text'
                      }`}
                    >
                      <span className="truncate text-left">{opt.label}</span>
                      {isSelected && <Check size={13} strokeWidth={2.5} className="ml-2 shrink-0 text-accent" />}
                    </button>
                  </React.Fragment>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
