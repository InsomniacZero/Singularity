import { memo, useState } from 'react'
import { AlertCircle, ChevronLeft, ChevronRight, Compass, GitFork, Heart, History, MessageSquareWarning, RotateCcw, Sparkles, Star, TriangleAlert, Unlink, X } from 'lucide-react'
import type { StoredMessage } from '@/lib/types'
import { useSettingsStore, type AvatarShape } from '@/lib/store/useSettingsStore'
import { messageAnchorId } from '@/lib/scrollToMessage'
import { renderMessageText } from '@/lib/text/messageText'
import type { SfxConfig } from '@/lib/text/messageSegments'
import { confirmDialog } from '@/lib/store/useConfirmStore'
import { intentSpec } from '@/lib/dating/intent'
import { ImageMatrixLoader } from '@/components/ui/Loaders'

function avatarClass(shape: AvatarShape): string {
  switch (shape) {
    case 'circle':
      return 'rounded-full'
    case 'square':
      return 'rounded-none'
    case 'rectangle':
      return 'rounded-md w-9 h-12'
    case 'rounded':
    default:
      return 'rounded-lg'
  }
}

function Avatar({ name, shape, dataUrl }: { name: string; shape: AvatarShape; dataUrl?: string }) {
  const base = `flex h-9 w-9 shrink-0 items-center justify-center bg-bg-sunken text-xs font-semibold text-text-muted overflow-hidden ${avatarClass(shape)}`
  if (dataUrl) {
    return <img src={dataUrl} alt={name} className={base + ' object-cover'} />
  }
  return <div className={base}>{name.slice(0, 2).toUpperCase()}</div>
}

interface MessageBubbleProps {
  message: StoredMessage
  avatarDataUrl?: string
  isStreaming?: boolean
  streamingText?: string
  /** Briefly highlighted after being scrolled to from a search result or the pinned-messages panel. */
  isHighlighted?: boolean
  /** SFX-burst policy for this message's speaker (global toggle + their `sfxWords`). */
  sfx?: SfxConfig
  // Every callback below takes this message's own id as its first argument, rather than
  // `MessageLog` pre-binding a fresh `() => onX(m.id)` closure per message per render — the whole
  // point of wrapping this component in `memo` below is to skip re-rendering a bubble whose props
  // haven't really changed (most of them, on every token streamed into a DIFFERENT bubble); a
  // freshly-allocated closure prop would defeat that by never comparing equal across renders.
  // `MessageLog` passes its own already-stable, already-id-taking callbacks straight through.
  onEdit: (id: string, text: string) => void
  onDelete: (id: string) => void
  onRewind: (id: string) => void
  onRegenerate: (id: string) => void
  /** Item 4's mid-scene correction: re-generates this reply with a one-shot, explicit correction folded in (`dating/steer.ts`) — never touches the chat, the card, or any persistent prompt section. */
  onSteer: (id: string, steerText: string) => void
  onSwipe: (id: string, dir: 'left' | 'right') => void
  onFork: (id: string) => void
  onTogglePin: (id: string) => void
}

export const MessageBubble = memo(function MessageBubble({
  message,
  avatarDataUrl,
  isStreaming,
  streamingText,
  isHighlighted,
  sfx,
  onEdit,
  onDelete,
  onRewind,
  onRegenerate,
  onSteer,
  onSwipe,
  onFork,
  onTogglePin,
}: MessageBubbleProps) {
  const chatStyle = useSettingsStore((s) => s.chatStyle)
  const avatarShape = useSettingsStore((s) => s.avatarShape)
  const showTimestamps = useSettingsStore((s) => s.showTimestamps)
  const showTokenCounts = useSettingsStore((s) => s.showTokenCounts)
  const clickToEdit = useSettingsStore((s) => s.clickToEdit)
  const regexScripts = useSettingsStore((s) => s.regexScripts)

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.text)
  // Item 4's steer popover: a one-shot correction typed here goes straight to `regenerateWithSteer`
  // and is never persisted anywhere — closing/cancelling just discards it, same as never opening it.
  const [steering, setSteering] = useState(false)
  const [steerDraft, setSteerDraft] = useState('')

  const isUser = message.role === 'user'
  const displayText = isStreaming ? streamingText ?? '' : message.text
  const swipes = message.swipes ?? []
  const canSwipe = !isUser && swipes.length > 0 && !isStreaming
  // Text stays empty on a failed generation — see `useChatSession.ts` — rather than persisting an
  // error string as the character's actual dialogue, which would otherwise get fed back into
  // every future prompt. The failure itself is shown here, driven by the flag, not by content.
  const showFailedIndicator = !isUser && message.failed && !isStreaming
  // Item 8: durable alternative to a one-shot toast — see `types.ts`'s `boundaryFlag` doc comment.
  // Additive, not a replacement for the text (unlike the failed indicator above): the reply itself
  // is still real, just flagged for the player's own judgment call.
  const showBoundaryFlag = !isUser && !!message.boundaryFlag && !isStreaming
  // Same durable, player-reviewed pattern as `boundaryFlag` above — see `dating/agencyGuard.ts`'s `detectPersonaAgencyViolation`.
  const showPovFlag = !isUser && !!message.povFlag && !isStreaming
  // Item 11: same durable, player-reviewed pattern again — see `types.ts`'s `explicitQualityFlag`
  // doc comment and `dating/intimacyScene.ts`'s `detectExplicitAntiPatternUsed`.
  const showExplicitQualityFlag = !isUser && !!message.explicitQualityFlag && !isStreaming
  // Same durable pattern once more, for a reply that contradicted the tracked scene state — see
  // `dating/continuityGuard.ts`. This one has usually already earned an automatic retry; the badge
  // is what's left when the retry was spent or the second attempt broke continuity too.
  const showContinuityFlag = !isUser && !!message.continuityFlag && !isStreaming

  const startEdit = () => {
    if (!clickToEdit || isStreaming) return
    setDraft(message.text)
    setEditing(true)
  }
  const commitEdit = () => {
    setEditing(false)
    if (draft !== message.text) onEdit(message.id, draft)
  }

  const closeSteer = () => {
    setSteering(false)
    setSteerDraft('')
  }
  const submitSteer = () => {
    const trimmed = steerDraft.trim()
    closeSteer()
    if (trimmed) onSteer(message.id, trimmed)
  }
  // A small inline popover anchored to the Steer button itself — same click-outside-backdrop
  // technique `ChatsPanel.tsx`'s row menu uses, kept local here rather than a full `Modal` since
  // this is a single short-lived textarea, not a standalone screen.
  const steerControl = (
    <span className="relative">
      <button
        onClick={() => setSteering((v) => !v)}
        className={`flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken ${steering ? 'bg-bg-sunken text-accent' : 'hover:text-text'}`}
        title="Steer. Correct this reply and regenerate"
        aria-label="Steer this reply"
      >
        <Compass size={13} strokeWidth={2} />
      </button>
      {steering && (
        <>
          <div className="fixed inset-0 z-40" onClick={closeSteer} />
          <div
            className="absolute bottom-full right-0 z-50 mb-1.5 w-64 rounded-xl border border-border/80 bg-bg-elevated/95 p-2.5 shadow-xl backdrop-blur-md"
            onClick={(e) => e.stopPropagation()}
          >
            <textarea
              autoFocus
              value={steerDraft}
              onChange={(e) => setSteerDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitSteer()
                if (e.key === 'Escape') closeSteer()
              }}
              placeholder="e.g. stop escalating, she should pull back and change the subject"
              rows={2}
              className="w-full resize-none rounded-md bg-bg-sunken p-2 text-xs text-text outline-none ring-1 ring-accent/40"
            />
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <span className="text-[10px] text-text-muted">Regenerates with this correction. Nothing is saved.</span>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  onClick={closeSteer}
                  className="rounded-md px-2 py-1 text-[11px] text-text-muted transition-colors hover:bg-bg-sunken hover:text-text"
                >
                  Cancel
                </button>
                <button
                  onClick={submitSteer}
                  disabled={!steerDraft.trim()}
                  className="rounded-md bg-accent px-2 py-1 text-[11px] font-medium text-accent-text transition-opacity disabled:opacity-40"
                >
                  Regenerate
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </span>
  )

  const [illustrating, setIllustrating] = useState(false)

  const handleManualIllustrate = async () => {
    if (illustrating) return
    setIllustrating(true)
    try {
      const res = await fetch('/api/scene/illustrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: message.text,
          force: true,
        }),
      })
      if (res.ok) {
        const data = (await res.json()) as { url?: string }
        if (data?.url) {
          const { messagesApi } = await import('@/lib/api/client')
          await messagesApi.update(message.id, { images: [data.url] })
        }
      }
    } catch (err) {
      console.warn('Manual illustrate error:', err)
    } finally {
      setIllustrating(false)
    }
  }

  const imageStrip = (
    <>
      {message.images && message.images.length > 0 && (
        <div className="my-3 flex flex-col gap-2.5">
          {message.images.map((src, i) => (
            <div
              key={i}
              className="group relative overflow-hidden rounded-xl border border-white/10 bg-black/40 shadow-xl transition-all duration-300 hover:border-accent/40"
            >
              <img
                src={src}
                alt="Scene illustration"
                className="max-h-[460px] w-full object-cover transition-transform duration-700 ease-out group-hover:scale-[1.02]"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100 flex items-end justify-between p-3.5">
                <span className="flex items-center gap-1.5 rounded-lg bg-black/60 px-2.5 py-1 text-xs font-medium text-white/95 backdrop-blur-md border border-white/10 shadow-sm">
                  <Sparkles size={13} className="text-amber-400" />
                  Nano Banana Scene Art
                </span>
                <a
                  href={src}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-lg bg-accent/90 px-3 py-1 text-xs font-semibold text-accent-text shadow-md transition-all hover:bg-accent hover:shadow-lg"
                  onClick={(e) => e.stopPropagation()}
                >
                  Open Full
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
      {illustrating && (
        <div className="my-3">
          <ImageMatrixLoader label="Generating scene illustration via Nano Banana..." />
        </div>
      )}
    </>
  )

  const textBlock = editing ? (
    <textarea
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commitEdit}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) commitEdit()
        if (e.key === 'Escape') setEditing(false)
      }}
      className="w-full resize-none rounded-xl bg-bg-sunken p-2.5 text-sm text-text outline-none ring-1 ring-accent/40"
      rows={Math.min(12, Math.max(2, draft.split('\n').length))}
    />
  ) : (
    <div
      onClick={startEdit}
      className={`prose-rp whitespace-pre-wrap break-words text-sm leading-relaxed ${clickToEdit ? 'cursor-text' : ''}`}
    >
      {showFailedIndicator ? (
        <span className="flex items-center gap-1.5 text-danger">
          <TriangleAlert size={14} strokeWidth={2} className="shrink-0" />
          Generation failed. Try regenerating below.
        </span>
      ) : (
        renderMessageText(displayText, regexScripts, sfx)
      )}
      {isStreaming && <span className="cursor-blink font-mono">▋</span>}
    </div>
  )

  const meta = (
    <div className="flex items-center gap-0.5 text-[11px] text-text-muted">
      {showTimestamps && <span className="mr-1.5">{new Date(message.createdAt).toLocaleTimeString()}</span>}
      {showTokenCounts && message.tokenCount ? <span className="mr-1.5">{message.tokenCount} tok</span> : null}
      {canSwipe && (
        <span className="mr-1 flex items-center gap-0.5">
          <button
            onClick={() => onSwipe(message.id, 'left')}
            className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-text disabled:opacity-30"
            disabled={(message.activeSwipe ?? 0) === 0}
            aria-label="Previous swipe"
          >
            <ChevronLeft size={14} strokeWidth={2} />
          </button>
          <span className="px-0.5 tabular-nums">
            {(message.activeSwipe ?? 0) + 1}/{swipes.length}
          </span>
          <button
            onClick={() => onSwipe(message.id, 'right')}
            className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-text"
            aria-label="Next swipe"
          >
            <ChevronRight size={14} strokeWidth={2} />
          </button>
        </span>
      )}
      {!isStreaming && (
        <>
          <button
            onClick={handleManualIllustrate}
            disabled={illustrating}
            className={`flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-text ${illustrating ? 'animate-pulse text-accent' : message.images?.length ? 'text-amber-400' : 'hover:text-amber-400'}`}
            title="Illustrate this scene (Nano Banana)"
            aria-label="Illustrate scene"
          >
            <Sparkles size={13} strokeWidth={2} />
          </button>
          <button
            onClick={() => onTogglePin(message.id)}
            className={`flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken ${message.pinned ? 'text-accent' : 'hover:text-text'}`}
            title={message.pinned ? 'Unpin' : 'Pin this moment'}
            aria-label={message.pinned ? 'Unpin message' : 'Pin message'}
          >
            <Star size={13} strokeWidth={2} fill={message.pinned ? 'currentColor' : 'none'} />
          </button>
          <button
            onClick={() => onRegenerate(message.id)}
            className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-text"
            title="Regenerate"
            aria-label="Regenerate"
          >
            <RotateCcw size={13} strokeWidth={2} />
          </button>
          {steerControl}
          <button
            onClick={() => onFork(message.id)}
            className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-text"
            title="Fork chat from here"
            aria-label="Fork chat from here"
          >
            <GitFork size={13} strokeWidth={2} />
          </button>
          <button
            onClick={async () => {
              const ok = await confirmDialog({
                title: 'Rewind to here?',
                body: 'Deletes this message and everything after it in this chat. Unlike forking, the discarded messages are not kept anywhere.',
                confirmLabel: 'Rewind',
                tone: 'danger',
              })
              if (ok) onRewind(message.id)
            }}
            className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-danger"
            title="Rewind to here (delete this and everything after)"
            aria-label="Rewind to here. Delete this message and everything after it"
          >
            <History size={13} strokeWidth={2} />
          </button>
          <button
            onClick={() => onDelete(message.id)}
            className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-sunken hover:text-danger"
            title="Delete"
            aria-label="Delete message"
          >
            <X size={13} strokeWidth={2} />
          </button>
        </>
      )}
    </div>
  )
  // Meta (timestamp, regenerate/delete, swipe) only appears on hover — keeps the resting
  // conversation calm and free of per-line chrome, matching the reference screens. Forced visible
  // while the steer popover is open: it's a child of this row, and CSS opacity is inherited by
  // descendants regardless of position, so it would otherwise vanish (while still interactive) the
  // moment the pointer leaves the row to type into it.
  const metaHoverable = (
    <div className={`mt-1 h-6 transition-opacity ${steering ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>{meta}</div>
  )
  // Unlike the rest of `meta`, a pin needs to stay visible at rest — otherwise there's no way to
  // spot favorited moments while scrolling without hovering every single bubble.
  const pinBadge = message.pinned ? (
    <span className="inline-flex text-accent" title="Pinned">
      <Star size={12} strokeWidth={2} fill="currentColor" />
    </span>
  ) : null
  // Item 8: same "stays visible at rest" reasoning as the pin badge above — a toast at generation
  // time is easy to miss; this stays on the message for as long as the flag stands, so it's still
  // there whenever the player actually looks. See `types.ts`'s `boundaryFlag` doc comment.
  const boundaryBadge = showBoundaryFlag ? (
    <span className="inline-flex text-warning" title={`May have crossed a stated limit: "${message.boundaryFlag}". Worth a regenerate if it reads wrong.`}>
      <TriangleAlert size={12} strokeWidth={2} />
    </span>
  ) : null
  // Distinct icon from `boundaryBadge` (a circle, not a triangle) so the two read as different
  // categories of flag at a glance, even though both share the same "worth a regenerate" severity
  // and styling otherwise.
  const povBadge = showPovFlag ? (
    <span
      className="inline-flex text-warning"
      title={`May have narrated your own reaction on your behalf: "${message.povFlag}". Worth a regenerate if it reads wrong.`}
    >
      <AlertCircle size={12} strokeWidth={2} />
    </span>
  ) : null
  // A third, distinct icon again — this one a prose-quality miss (the model actually used a phrase
  // it was told to avoid), not a boundary or POV violation, so it reads as its own category too.
  const explicitQualityBadge = showExplicitQualityFlag ? (
    <span
      className="inline-flex text-warning"
      title={`This reply used the stock phrase "${message.explicitQualityFlag}" it was told to avoid. Worth a regenerate if it reads wrong.`}
    >
      <MessageSquareWarning size={12} strokeWidth={2} />
    </span>
  ) : null
  // A fourth distinct icon — a break in what the scene already established, rather than a limit, a
  // POV slip, or a prose tell.
  const continuityBadge = showContinuityFlag ? (
    <span className="inline-flex text-warning" title={`This reply contradicted the scene: ${message.continuityFlag}. Worth a regenerate if it reads wrong.`}>
      <Unlink size={12} strokeWidth={2} />
    </span>
  ) : null
  // 10b: how the player tagged this line's intent. Shown at rest (not hover-only) — it's real
  // context for how the exchange should read.
  const intentBadge = (() => {
    const spec = intentSpec(message.intent)
    if (!spec) return null
    return (
      <span className="rounded-md bg-accent/12 px-1.5 py-0.5 text-[10px] font-medium text-accent" title={spec.hint}>
        {spec.label}
      </span>
    )
  })()
  // The user's own direct question: once sent, a line drafted from the Relationship panel's
  // Unlocks tab (a kiss spot/position/toy/activity) reads exactly like ordinary freeform text —
  // nothing marked which catalog entry it came from, so a player scrolling back later (or who just
  // forgot) had no way to tell. Same "stays visible at rest" reasoning as `intentBadge` above, not
  // hover-only, since this is exactly the kind of thing a player wants to spot while skimming, not
  // hunt for.
  const intimacyActionBadge = message.intimacyAction ? (
    <span
      className="inline-flex items-center gap-1 rounded-md bg-romance/12 px-1.5 py-0.5 text-[10px] font-medium text-romance"
      title={`Sent from the Relationship panel's Unlocks tab (${message.intimacyAction.category.replace('_', ' ')}): "${message.intimacyAction.label}"`}
    >
      <Heart size={9} strokeWidth={2.25} className="shrink-0" />
      {message.intimacyAction.label}
    </span>
  ) : null
  const anchorId = messageAnchorId(message.id)
  const highlightClass = isHighlighted ? 'bg-accent/10' : ''

  if (chatStyle === 'document') {
    return (
      <div id={anchorId} className={`group rounded-lg py-2 transition-colors duration-1000 ${highlightClass}`}>
        <span className={`font-display ${isUser ? 'text-accent' : 'text-text'}`}>{message.name}: </span>
        {pinBadge} {boundaryBadge} {povBadge} {explicitQualityBadge} {continuityBadge} {intentBadge} {intimacyActionBadge}{' '}
        {imageStrip}
        <span className="prose-rp whitespace-pre-wrap break-words text-sm leading-relaxed">
          {editing ? (
            textBlock
          ) : (
            <>
              {showFailedIndicator ? (
                <span className="inline-flex items-center gap-1.5 text-danger">
                  <TriangleAlert size={14} strokeWidth={2} className="shrink-0" />
                  Generation failed. Try regenerating below.
                </span>
              ) : (
                renderMessageText(displayText, regexScripts, sfx)
              )}
              {isStreaming && <span className="cursor-blink font-mono">▋</span>}
            </>
          )}
        </span>
        <span className={`ml-2 transition-opacity ${steering ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>{meta}</span>
      </div>
    )
  }

  if (chatStyle === 'bubbles') {
    return (
      <div
        id={anchorId}
        className={`group flex gap-3 rounded-lg py-2 transition-colors duration-1000 ${highlightClass} ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
      >
        <Avatar name={message.name} shape={avatarShape} dataUrl={avatarDataUrl} />
        <div className={`flex max-w-[75%] flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <div
            className={`rp-bubble rounded-xl border border-border/60 shadow-sm px-4 py-2.5 ${
              isUser
                ? 'rp-bubble-user bg-msg-user text-accent-text rounded-tr-xs'
                : 'rp-bubble-char bg-msg-char text-text rounded-tl-xs'
            }`}
          >
            {imageStrip}
            {textBlock}
          </div>
          <div className="flex items-center gap-1.5">
            {pinBadge}
            {boundaryBadge}
            {povBadge}
            {explicitQualityBadge}
            {continuityBadge}
            {intentBadge}
            {intimacyActionBadge}
            {metaHoverable}
          </div>
        </div>
      </div>
    )
  }

  // flat (default): log-like, full width, no dividers — just generous vertical rhythm
  return (
    <div id={anchorId} className={`group flex gap-3 rounded-lg py-3.5 transition-colors duration-1000 ${highlightClass}`}>
      <Avatar name={message.name} shape={avatarShape} dataUrl={avatarDataUrl} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-sm font-display text-text">
          {message.name}
          {pinBadge}
          {boundaryBadge}
          {povBadge}
          {explicitQualityBadge}
          {continuityBadge}
          {intentBadge}
          {intimacyActionBadge}
        </div>
        {imageStrip}
        {textBlock}
        {metaHoverable}
      </div>
    </div>
  )
})
