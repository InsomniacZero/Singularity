import { useState } from 'react'
import { MapPin, Trash2 } from 'lucide-react'
import type { Scene, ScenePolicy } from '@/lib/types'
import type { DayPhase } from '@/lib/world/calendar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'
import { TextAreaField } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'

const TIME_OF_DAY: { value: DayPhase | 'clock'; label: string }[] = [
  { value: 'clock', label: 'World clock' },
  { value: 'morning', label: 'Morning' },
  { value: 'afternoon', label: 'Afternoon' },
  { value: 'evening', label: 'Evening' },
  { value: 'night', label: 'Night' },
]

const POLICIES: { id: ScenePolicy; label: string; hint: string }[] = [
  {
    id: 'manual',
    label: 'Manual',
    hint: 'You pick who replies each turn from the composer’s "reply as" menu, exactly like today.',
  },
  {
    id: 'round_robin',
    label: 'Round-robin',
    hint: 'Cycles through everyone present in a fixed order, one turn each.',
  },
  {
    id: 'director',
    label: 'AI director',
    hint: 'A quick read of the scene picks whoever would naturally respond. Falls back to the primary if it can’t decide.',
  },
  {
    id: 'mention',
    label: '@Mention',
    hint: 'Write "@Name" in your own message to address them directly. Otherwise falls back to the primary.',
  },
]

export function ScenePanel({
  scene,
  locationArt,
  onDeleteLocationArt,
  participantIds,
  otherCharacters,
  onClose,
  onSave,
  onSaveParticipants,
}: {
  scene: Scene | undefined
  locationArt?: Record<string, string>
  onDeleteLocationArt?: (locKey: string) => Promise<void> | void
  /** Who's currently in the roster (`Chat.participants`) besides the primary. */
  participantIds: string[]
  /** Every character that could be invited in — the primary is never in this list. */
  otherCharacters: { id: string; name: string }[]
  onClose: () => void
  onSave: (patch: Partial<Scene> | null) => Promise<void>
  /** Previously there was no way to change `Chat.participants` after the chat was created at all —
   *  "a friend walks in" mid-scene, or someone leaving, meant abandoning the chat and starting a
   *  fresh one with the right roster from the start. */
  onSaveParticipants: (ids: string[]) => Promise<void>
}) {
  const [location, setLocation] = useState(scene?.location ?? '')
  const [atmosphere, setAtmosphere] = useState(scene?.atmosphere ?? '')
  const [timeOfDay, setTimeOfDay] = useState<DayPhase | 'clock'>(scene?.timePhase ?? 'clock')
  const [turnPolicy, setTurnPolicy] = useState<ScenePolicy>(scene?.turnPolicy ?? 'manual')
  const [participants, setParticipants] = useState<string[]>(participantIds)
  const [busy, setBusy] = useState(false)

  const toggleParticipant = (id: string) =>
    setParticipants((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]))

  const participantsChanged =
    participants.length !== participantIds.length || participants.some((id) => !participantIds.includes(id))

  const save = async (payload: Partial<Scene> | null) => {
    setBusy(true)
    try {
      if (participantsChanged) await onSaveParticipants(participants)
      await onSave(payload)
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title="Scene"
      description="Frames where this group scene is happening and who replies next. Section 4/12's Scene entity. Location/atmosphere fold into the prompt the same way an active event's own does; turn policy only matters once more than one character is present."
      size="lg"
      scrollable
    >
      <div className="flex-1 overflow-y-auto">
        {otherCharacters.length > 0 && (
          <div className="mb-4">
            <span className="mb-1 block text-xs font-medium text-text-muted">Who's in this scene</span>
            <div className="flex flex-wrap gap-1.5">
              {otherCharacters.map((c) => (
                <Chip key={c.id} on={participants.includes(c.id)} onClick={() => toggleParticipant(c.id)}>
                  {c.name}
                </Chip>
              ))}
            </div>
            <p className="mt-1.5 text-[11px] text-text-muted">
              Add someone mid-scene, or drop someone who's left. Past messages keep the name/art they were sent
              with either way, this only changes who can speak next.
            </p>
          </div>
        )}

        <TextAreaField
          label="Location"
          rows={2}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="e.g. The campus café, late afternoon"
        />

        {locationArt && Object.keys(locationArt).length > 0 && (
          <div className="mb-4 -mt-2">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="flex items-center gap-1 text-xs font-medium text-text-muted">
                <MapPin className="h-3.5 w-3.5 text-accent" />
                Remembered Places ({Object.keys(locationArt).length})
              </span>
              <span className="text-[10px] text-text-muted">1080p Backdrops</span>
            </div>
            <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
              {Object.entries(locationArt).map(([locKey, url]) => (
                <div
                  key={locKey}
                  className="group relative flex flex-col overflow-hidden rounded-xl border border-white/10 bg-bg-sunken p-1.5 transition-all hover:border-accent/40"
                >
                  <div
                    className="relative aspect-video w-full overflow-hidden rounded-lg bg-black/40 cursor-pointer"
                    onClick={() => setLocation(locKey)}
                    title={`Click to set location to: ${locKey}`}
                  >
                    <img src={url} alt={locKey} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-70 group-hover:opacity-40" />
                    <span className="absolute bottom-1 left-1.5 right-1.5 truncate text-[11px] font-semibold text-white drop-shadow">
                      {locKey}
                    </span>
                  </div>
                  {onDeleteLocationArt && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onDeleteLocationArt(locKey)
                      }}
                      className="absolute top-2.5 right-2.5 rounded-md bg-black/70 p-1 text-white/70 opacity-0 transition-opacity hover:bg-rose-600 hover:text-white group-hover:opacity-100"
                      title="Forget this backdrop"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-text-muted">
              Click any place above to jump back to it. Nano Banana recalls and maintains that backdrop.
            </p>
          </div>
        )}

        <TextAreaField
          label="Atmosphere"
          rows={2}
          value={atmosphere}
          onChange={(e) => setAtmosphere(e.target.value)}
          placeholder="e.g. Tense, right after an argument"
        />

        <div className="mb-4">
          <span className="mb-1 block text-xs font-medium text-text-muted">Time of day</span>
          <SegmentedControl
            fill
            options={TIME_OF_DAY}
            value={timeOfDay}
            onChange={setTimeOfDay}
          />
          <p className="mt-1.5 text-[11px] text-text-muted">
            Overrides the shared world clock's time-of-day for this chat only. Useful once the story has drifted past it.
            Auto-follows what you narrate ("the next morning", "at lunch"); the weekday still comes from the world clock.
          </p>
        </div>

        <div className="mb-3">
          <span className="mb-1 block text-xs font-medium text-text-muted">Turn policy</span>
          <div className="flex flex-col gap-1.5">
            {POLICIES.map((p) => (
              <label
                key={p.id}
                className="flex cursor-pointer items-start gap-2.5 rounded-xl bg-bg-sunken px-3 py-2.5 text-sm"
              >
                <input
                  type="radio"
                  name="scene-turn-policy"
                  className="mt-0.5"
                  checked={turnPolicy === p.id}
                  onChange={() => setTurnPolicy(p.id)}
                />
                <span>
                  <span className="block text-text">{p.label}</span>
                  <span className="block text-[11px] text-text-muted">{p.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-5 flex shrink-0 items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => save(null)} disabled={busy || !scene}>
          Clear scene
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() =>
              save({
                location: location.trim() || null,
                atmosphere: atmosphere.trim() || null,
                timePhase: timeOfDay === 'clock' ? null : timeOfDay,
                turnPolicy,
                // A fresh policy pick starts its own bookkeeping from scratch rather than
                // inheriting a stale round-robin index from a previous policy.
                roundRobinIndex: turnPolicy === scene?.turnPolicy && !participantsChanged ? scene?.roundRobinIndex : 0,
              })
            }
            disabled={busy}
          >
            Save
          </Button>
        </div>
      </div>
    </Modal>
  )
}
