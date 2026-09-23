import {
  BookOpen,
  CircleUserRound,
  GalleryHorizontalEnd,
  Globe,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings as SettingsIcon,
  Sparkles,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useSettingsStore } from '@/lib/store/useSettingsStore'

export type ViewId = 'chat' | 'assistant' | 'characters' | 'worlds' | 'personas' | 'worldinfo' | 'gallery' | 'settings'

export const NAV: { id: ViewId; label: string; icon: LucideIcon }[] = [
  { id: 'chat', label: 'Chat', icon: MessageCircle },
  { id: 'assistant', label: 'Assistant', icon: Sparkles },
  { id: 'characters', label: 'Characters', icon: Users },
  { id: 'worlds', label: 'Worlds', icon: Globe },
  { id: 'personas', label: 'Personas', icon: CircleUserRound },
  { id: 'worldinfo', label: 'World Info', icon: BookOpen },
  { id: 'gallery', label: 'Gallery', icon: GalleryHorizontalEnd },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
]

export function Sidebar({
  view,
  onChange,
  onOpenPalette,
}: {
  view: ViewId
  onChange: (v: ViewId) => void
  /** Opens the command palette (Ctrl/Cmd-K) — desktop-only trigger; the mobile bottom bar has no
   *  room to spare and a keyboard shortcut isn't the point on a touch device anyway. */
  onOpenPalette?: () => void
}) {
  const expanded = useSettingsStore((s) => s.sidebarExpanded)
  const setExpanded = useSettingsStore((s) => s.setSidebarExpanded)

  return (
    <nav
      className={`fixed inset-x-0 bottom-0 z-30 flex items-center justify-around gap-0.5 border-t border-border/70 bg-bg-elevated/95 px-1 py-1.5 backdrop-blur-md
        md:static md:inset-auto md:z-auto md:flex-col md:justify-start md:gap-1 md:border-t-0 md:border-r md:border-border/70 md:bg-bg-elevated md:py-3.5 md:transition-[width] md:duration-200 ${
        expanded ? 'md:w-56 md:px-2.5' : 'md:w-14 md:items-center md:px-1.5'
      }`}
    >
      {/* Editorial Brand Header (Desktop) */}
      <div className="hidden w-full items-center justify-between pb-3.5 pt-1 px-2 border-b border-border/60 md:flex">
        {expanded ? (
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-white font-mono font-bold text-xs shadow-sm">
              T
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-sans font-bold text-xs tracking-tight text-text truncate">
                TAVERN
              </span>
              <span className="font-mono text-[9px] uppercase tracking-wider text-text-muted/80 truncate">
                Roleplay Studio
              </span>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex h-7 w-7 items-center justify-center rounded-md bg-accent text-white font-mono font-bold text-xs shadow-sm">
            T
          </div>
        )}
      </div>

      {onOpenPalette && (
        <button
          onClick={onOpenPalette}
          data-tooltip="Search everywhere (Ctrl/Cmd-K)"
          aria-label="Search everywhere"
          className={`my-1 hidden items-center rounded-lg text-text-muted transition-all duration-150 active:scale-[0.98] hover:bg-bg-sunken hover:text-text md:flex ${
            expanded ? 'w-full justify-start gap-2.5 px-3 py-2 text-xs' : 'md:h-9 md:w-9 md:justify-center'
          }`}
        >
          <Search size={16} strokeWidth={2} className="shrink-0 text-text-muted" />
          {expanded && (
            <>
              <span className="font-medium text-text-muted">Search</span>
              <kbd className="ml-auto font-mono text-[10px] text-text-muted/70 bg-bg-sunken px-1.5 py-0.5 rounded border border-border/60">
                ⌘K
              </kbd>
            </>
          )}
        </button>
      )}

      <div className="flex flex-1 w-full flex-row md:flex-col gap-0.5 md:gap-1">
        {NAV.map((item) => {
          const isActive = view === item.id
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              data-tooltip={!expanded ? item.label : undefined}
              aria-label={item.label}
              className={`flex flex-1 items-center justify-center rounded-lg text-xs transition-all duration-150 active:scale-[0.98] md:flex-initial ${
                expanded
                  ? 'md:w-full md:justify-start md:gap-2.5 md:px-3 md:py-2'
                  : 'md:h-9 md:w-9'
              } h-11 w-11 ${
                isActive
                  ? 'bg-accent/12 text-accent font-semibold md:border-l-2 md:border-accent'
                  : 'text-text-muted hover:bg-bg-sunken hover:text-text md:border-l-2 md:border-transparent'
              }`}
            >
              <item.icon size={17} strokeWidth={isActive ? 2.25 : 1.75} className="shrink-0" />
              {expanded && <span className="hidden md:inline font-medium">{item.label}</span>}
            </button>
          )
        })}
      </div>

      <button
        onClick={() => setExpanded(!expanded)}
        data-tooltip={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        className={`hidden items-center rounded-lg text-text-muted transition-all duration-150 active:scale-[0.96] hover:bg-bg-sunken hover:text-text md:mt-auto md:flex ${
          expanded ? 'w-full justify-start gap-2.5 px-3 py-2 text-xs' : 'md:h-9 md:w-9 md:justify-center'
        }`}
      >
        {expanded ? (
          <>
            <PanelLeftClose size={16} strokeWidth={1.75} />
            <span className="text-text-muted text-xs">Collapse</span>
          </>
        ) : (
          <PanelLeftOpen size={16} strokeWidth={1.75} />
        )}
      </button>
    </nav>
  )
}
