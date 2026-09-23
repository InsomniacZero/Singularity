import { useMemo, useState } from 'react'
import { useApiQuery } from '@/lib/hooks/useApiQuery'
import { charactersApi, chatsApi, personasApi } from '@/lib/api/client'
import { useSettingsStore } from '@/lib/store/useSettingsStore'
import { ViewShell } from '@/components/ui/ViewShell'
import { EmptyState } from '@/components/ui/EmptyState'
import { CustomSelect } from '@/components/ui/CustomSelect'

export function GalleryView() {
  const characters = useApiQuery('characters', () => charactersApi.list(), []) ?? []
  const chats = useApiQuery('chats', () => chatsApi.list(), []) ?? []
  const personas = useApiQuery('personas', () => personasApi.list(), []) ?? []
  const activePersonaId = useSettingsStore((s) => s.activePersonaId)
  const [personaFilter, setPersonaFilter] = useState<string>(activePersonaId ?? 'all')

  const chatsForFilter = useMemo(() => {
    if (personaFilter === 'all') return chats
    return chats.filter((c) => c.personaId === personaFilter)
  }, [chats, personaFilter])

  const unlockedByCharacter = useMemo(() => {
    const map = new Map<string, Set<string>>()
    for (const chat of chatsForFilter) {
      if (!map.has(chat.characterId)) map.set(chat.characterId, new Set())
      for (const id of chat.unlockedGalleryIds ?? []) map.get(chat.characterId)!.add(id)
    }
    return map
  }, [chatsForFilter])

  const affectionByCharacter = useMemo(() => {
    const map = new Map<string, number>()
    for (const chat of chatsForFilter) {
      map.set(chat.characterId, Math.max(map.get(chat.characterId) ?? 0, chat.affection ?? 0))
    }
    return map
  }, [chatsForFilter])

  return (
    <ViewShell
      title="Gallery"
      width="wide"
      description="CG art unlocks as a relationship deepens: by raising affection and hitting key story beats in chat events."
      actions={
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <span>Persona</span>
          <CustomSelect
            value={personaFilter}
            onChange={(e) => setPersonaFilter(e.target.value)}
            className="w-44"
          >
            <option value="all">All personas</option>
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </CustomSelect>
        </div>
      }
    >
      <div className="space-y-8">
        {characters.map((character) => {
          const gallery = character.gallery ?? []
          if (gallery.length === 0) return null
          const cgs = gallery.filter((g) => !g.isEnding)
          const endings = gallery.filter((g) => g.isEnding)
          const unlocked = unlockedByCharacter.get(character.id) ?? new Set<string>()
          const affection = affectionByCharacter.get(character.id) ?? 0
          return (
            <section key={character.id}>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text">{character.card.name}</h3>
                <div className="text-xs text-text-muted">
                  {unlocked.size}/{gallery.length} unlocked • affection {affection}
                </div>
              </div>
              {cgs.length > 0 && (
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                  {cgs.map((entry) => {
                    const isUnlocked = unlocked.has(entry.id) || affection >= entry.unlockAffection
                    return (
                      <div key={entry.id} className="group relative overflow-hidden rounded-xl border border-border/80 bg-bg-elevated shadow-sm transition-all duration-200 hover:border-accent/40">
                        {entry.imageUrl ? (
                          <img
                            src={entry.imageUrl}
                            className={`aspect-[4/3] w-full object-cover transition-transform duration-300 ${isUnlocked ? 'group-hover:scale-[1.03]' : 'blur-sm grayscale'}`}
                          />
                        ) : (
                          <div className="flex aspect-[4/3] w-full items-center justify-center text-xs text-text-muted">No art</div>
                        )}
                        {!isUnlocked && (
                          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                            <div className="rounded-md bg-black/75 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
                              Unlock at {entry.unlockAffection}
                            </div>
                          </div>
                        )}
                        <div className="p-3">
                          <div className="text-xs font-medium text-text">{entry.title}</div>
                          {entry.unlockHint && <div className="mt-1 text-[11px] text-text-muted">{entry.unlockHint}</div>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
              {endings.length > 0 && (
                <div className="mt-5">
                  <div className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-romance">Endings</div>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                    {endings.map((entry) => {
                      // Endings unlock only via reaching Sweethearts (see `unlockedEndingIds`) — never
                      // through `unlockAffection`, which is unused/ignored for `isEnding` entries.
                      const isUnlocked = unlocked.has(entry.id)
                      return (
                        <div
                          key={entry.id}
                          className={`group relative overflow-hidden rounded-xl border bg-bg-elevated transition-all duration-200 ${isUnlocked ? 'border-romance/80 shadow-md ring-1 ring-romance/30' : 'border-border/80'}`}
                        >
                          {entry.imageUrl ? (
                            <img
                              src={entry.imageUrl}
                              className={`aspect-[4/3] w-full object-cover transition-transform duration-300 ${isUnlocked ? 'group-hover:scale-[1.03]' : 'blur-sm grayscale'}`}
                            />
                          ) : (
                            <div className="flex aspect-[4/3] w-full items-center justify-center text-xs text-text-muted">No art</div>
                          )}
                          {!isUnlocked && (
                            <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                              <div className="rounded-md bg-black/75 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">Reach Sweethearts</div>
                            </div>
                          )}
                          <div className="p-3">
                            <div className="text-xs font-medium text-text">{entry.title}</div>
                            {entry.unlockHint && <div className="mt-1 text-[11px] text-text-muted">{entry.unlockHint}</div>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </section>
          )
        })}
      </div>

      {characters.every((c) => !c.gallery?.length) && (
        <EmptyState>
          No gallery art yet. Add CG images in a character's editor (Dating sim tab), then unlock them
          through affection milestones and story beats in chat.
        </EmptyState>
      )}
    </ViewShell>
  )
}
