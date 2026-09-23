import { useMemo, useState } from 'react'
import { useApiQuery } from '@/lib/hooks/useApiQuery'
import { charactersApi } from '@/lib/api/client'
import type { Character } from '@/lib/characters/cardSpec'
import { useSettingsStore } from '@/lib/store/useSettingsStore'
import { Button } from '@/components/ui/Button'
import { ViewShell } from '@/components/ui/ViewShell'
import { EmptyState } from '@/components/ui/EmptyState'
import { CustomSelect } from '@/components/ui/CustomSelect'

const UNTAGGED = 'Untagged'

export function CharacterList({
  onSelect,
  onCreateNew,
}: {
  onSelect: (character: Character) => void
  onCreateNew: () => void
}) {
  const characters = useApiQuery('characters', () => charactersApi.list(), []) ?? []
  const tagsAsFolders = useSettingsStore((s) => s.tagsAsFolders)
  const [activeFolder, setActiveFolder] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const groups = useMemo(() => {
    const map = new Map<string, Character[]>()
    for (const c of characters) {
      const tags = c.card.tags && c.card.tags.length > 0 ? c.card.tags : [UNTAGGED]
      for (const tag of tags) {
        if (!map.has(tag)) map.set(tag, [])
        map.get(tag)!.push(c)
      }
    }
    return map
  }, [characters])

  const sortedTags = useMemo(() => {
    const all = [...groups.keys()]
    const named = all
      .filter((t) => t !== UNTAGGED)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
    if (all.includes(UNTAGGED)) {
      return [...named, UNTAGGED]
    }
    return named
  }, [groups])

  const tagOptions = useMemo(() => {
    return [
      { value: '', label: `All Tags (${characters.length})` },
      ...sortedTags.map((tag) => ({
        value: tag,
        label: `${tag === UNTAGGED ? 'Untagged' : `/ ${tag}`} (${groups.get(tag)?.length ?? 0})`,
      })),
    ]
  }, [characters.length, sortedTags, groups])

  const visible = useMemo(() => {
    const base = tagsAsFolders && activeFolder ? (groups.get(activeFolder) ?? []) : characters
    const q = search.trim().toLowerCase()
    if (!q) return base
    return base.filter((c) =>
      c.card.name.toLowerCase().includes(q) ||
      (c.card.creator && c.card.creator.toLowerCase().includes(q))
    )
  }, [characters, tagsAsFolders, activeFolder, groups, search])

  return (
    <ViewShell
      title="Characters"
      width="wide"
      actions={
        <Button variant="primary" onClick={onCreateNew}>
          New character
        </Button>
      }
    >
      <div className="mb-6 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="relative w-full max-w-xs">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search characters…"
            className="w-full rounded-lg border border-border/80 bg-bg-sunken px-3 py-2 text-sm text-text outline-none transition-all placeholder:text-text-muted/60 focus:border-accent/60 focus:ring-1 focus:ring-accent/50"
          />
        </div>

        {tagsAsFolders && groups.size > 1 && (
          <div className="flex items-center gap-2 w-full sm:w-60">
            <div className="flex-1">
              <CustomSelect
                value={activeFolder ?? ''}
                onChange={(e) => setActiveFolder(e.target.value || null)}
                placeholder="All Tags"
                options={tagOptions}
              />
            </div>
            {activeFolder && (
              <button
                type="button"
                onClick={() => setActiveFolder(null)}
                className="shrink-0 rounded-md px-2.5 py-1.5 text-xs text-text-muted transition-colors hover:bg-bg-sunken hover:text-text active:scale-[0.98]"
                title="Reset tag filter"
              >
                Clear
              </button>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-5 lg:grid-cols-4">
        {visible.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelect(c)}
            className="group rounded-xl border border-border/80 bg-bg-elevated p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-xl active:scale-[0.99]"
          >
            <div className="portrait-frame mb-3 aspect-[3/4] w-full overflow-hidden rounded-lg border border-border/50 bg-bg-sunken">
              {c.avatarDataUrl ? (
                <img src={c.avatarDataUrl} alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]" />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-bg-sunken text-2xl font-bold text-text-muted">
                  {c.card.name.slice(0, 1).toUpperCase()}
                </div>
              )}
            </div>
            <div className="truncate px-0.5 text-sm font-semibold text-text group-hover:text-accent transition-colors">{c.card.name}</div>
            <div className="truncate px-0.5 text-xs text-text-muted">{c.card.creator || ' '}</div>
          </button>
        ))}
        {visible.length === 0 && (
          <EmptyState
            className="col-span-full"
            action={
              <Button variant="primary" onClick={onCreateNew}>
                New character
              </Button>
            }
          >
            {search || activeFolder
              ? 'No characters match that filter.'
              : 'No characters yet. Create one from scratch, start from a bundled template, generate one with AI, or import a SillyTavern card.'}
          </EmptyState>
        )}
      </div>
    </ViewShell>
  )
}
