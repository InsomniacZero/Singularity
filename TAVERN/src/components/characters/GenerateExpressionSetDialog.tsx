import { useEffect, useRef, useState } from 'react'
import { useSettingsStore } from '@/lib/store/useSettingsStore'
import { createImageBackend } from '@/lib/api/createImageBackend'
import { errorMessage } from '@/lib/store/useToastStore'
import { urlToDataUrl } from '@/lib/characters/pack'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'
import { CheckCircle2, Clock, Sparkles, Upload, X } from 'lucide-react'

interface ExpressionOption {
  id: string
  label: string
  hasSprite: boolean
}

const EMOTION_POSE_MAP: Record<string, string> = {
  neutral: 'calm composed expression, gentle gaze, both full shoulders relaxed and completely visible inside frame',
  happy: 'cheerful bright smile, sparkling lively eyes, one hand raised near cheek in a friendly wave, elbow kept tucked close to torso and fully in-frame',
  smirk: 'playful sly smirk, confident knowing gaze, hand touching chin with elbow tucked against chest inside frame',
  laughing: 'mouth open laughing joyfully with crinkled eyes, one hand covering mouth while giggling, elbow tucked close inside frame',
  sad: 'downcast melancholic expression, gentle sorrowful eyes, one hand resting on chest, shoulders drooping naturally in-frame',
  crying: 'tearful emotional face with tears glistening on cheeks, one hand gently wiping away tears with elbow held inside frame',
  angry: 'fierce intense glare, furrowed eyebrows, clenched teeth in a frustrated scowl, tense full shoulders in-frame',
  annoyed: 'irritated pout with furrowed brow, head turned slightly away in displeasure, arms resting close to torso',
  surprised: 'wide rounded eyes and parted lips in sudden shock, hands raised in front of upper chest in astonishment, elbows tucked within frame borders',
  scared: 'fearful trembling expression, wide panicked pupils, hands held defensively close against upper chest, elbows within frame',
  disgust: 'recoiling grimace with curled lip, head turned slightly away, one hand raised defensively near collarbone with elbow kept inside frame',
  confusion: 'quizzical perplexed look with head tilted, one index finger placed curiously on cheek, elbow tucked close to chest within frame',
  pain: 'wincing in discomfort with strained tightly shut eyes, one hand clutching collar or chest, elbow kept inside frame',
  relief: 'soft sigh of relief, gentle relaxed smile with closed eyes, one hand resting flat over heart on upper chest, elbow inside frame',
  blush: 'cheeks flushed bright red, shy flustered gaze looking downward, fingertips touching warm blushing cheeks, elbows tucked inward inside frame',
  loving: 'tender warm affectionate gaze, soft adoring smile, hands clasped together gently against heart, elbows close to sides inside frame',
  flirty: 'charming playful wink, alluring smile, fingertips near lips or hair, elbow kept close to body within frame',
  smitten: 'starry-eyed entranced smile, deeply enamored rosy cheeks, hands pressed together beside cheek, elbows tucked safely in-frame',
  yearning: 'longing wistful expression, tender pleading eyes, one open hand held gently upward in front of chest within frame, elbow inside',
  sultry: 'half-lidded sensual gaze, seductive slight smile, one hand resting near collarbone with elbow tucked in-frame',
  aroused: 'intensely flushed cheeks, heavy parted breath, dazed passionate gaze, hand touching neck or collar with elbow kept in-frame',
  embarrassed: 'flustered mortified blush, averted eyes, hands covering blushing cheeks, elbows tucked inward inside frame',
  thinking: 'pensive thoughtful gaze looking upward, index finger resting on chin in deep contemplation, elbow tucked close to chest inside frame',
  determined: 'resolute focused gaze, confident firm set jaw, one fist raised firmly against upper chest, elbow kept within frame',
  sleepy: 'drowsy half-asleep eyes, small yawn, one hand rubbing tired eye, elbow tucked inward inside frame',
}

function formatDuration(totalSeconds: number): string {
  const secs = Math.max(0, Math.round(totalSeconds))
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const remainingSecs = secs % 60
  return `${mins}m${remainingSecs > 0 ? ` ${remainingSecs}s` : ''}`
}

export function GenerateExpressionSetDialog({
  expressions,
  initialPrompt,
  characterPortrait,
  characterName,
  onGenerated,
  onClose,
}: {
  expressions: ExpressionOption[]
  initialPrompt: string
  characterPortrait?: string
  characterName?: string
  onGenerated: (expressionId: string, dataUrl: string) => void
  onClose: () => void
}) {
  const [basePrompt, setBasePrompt] = useState(initialPrompt)
  const [referenceImage, setReferenceImage] = useState<string>(characterPortrait || '')
  const [isDragging, setIsDragging] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(() => new Set(expressions.filter((e) => !e.hasSprite).map((e) => e.id)))
  const [busy, setBusy] = useState(false)
  const [stopRequested, setStopRequested] = useState(false)
  const stopRef = useRef(false)
  const controllerRef = useRef<AbortController | null>(null)
  const startTimeRef = useRef<number>(0)

  useEffect(() => {
    if (characterPortrait) {
      if (characterPortrait.startsWith('data:')) {
        setReferenceImage(characterPortrait)
      } else {
        urlToDataUrl(characterPortrait).then((dataUrl) => {
          if (dataUrl) setReferenceImage(dataUrl)
        })
      }
    }
  }, [characterPortrait])

  useEffect(() => () => { stopRef.current = true; controllerRef.current?.abort() }, [])
  const [progress, setProgress] = useState<{ done: number; total: number; currentLabel: string | null; estRemainingSecs: number | null }>({
    done: 0,
    total: 0,
    currentLabel: null,
    estRemainingSecs: null,
  })
  const [results, setResults] = useState<{ succeeded: string[]; failed: string[] } | null>(null)

  const openMayhemApiKey = useSettingsStore((s) => s.openMayhemApiKey)
  const imageBackend = useSettingsStore((s) => s.imageBackend)
  const imageBackendBaseUrl = useSettingsStore((s) => s.imageBackendBaseUrl)
  const imageBackendUsername = useSettingsStore((s) => s.imageBackendUsername)
  const imageBackendPassword = useSettingsStore((s) => s.imageBackendPassword)
  const imageBackendModel = useSettingsStore((s) => s.imageBackendModel)

  const [concurrency, setConcurrency] = useState<number>(imageBackend === 'singularity' ? 3 : 2)
  const effectiveConcurrency = imageBackend === 'singularity' ? concurrency : 2
  const estSecsPerRound = imageBackend === 'singularity' ? 12 : 20
  const initialEstTotalSecs = Math.ceil(selected.size / effectiveConcurrency) * estSecsPerRound

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const handleFile = (file: File) => {
    if (!file.type.startsWith('image/')) return
    const reader = new FileReader()
    reader.onload = () => setReferenceImage(String(reader.result))
    reader.readAsDataURL(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  const canGenerate = !busy && selected.size > 0 && (Boolean(referenceImage) || Boolean(basePrompt.trim()))

  const generate = async () => {
    const targets = expressions.filter((e) => selected.has(e.id))
    if (!targets.length || busy || (!referenceImage && !basePrompt.trim())) return
    setBusy(true)
    setStopRequested(false)
    stopRef.current = false
    const controller = new AbortController()
    controllerRef.current = controller
    setResults(null)
    startTimeRef.current = Date.now()

    // Ensure reference image is resolved to a complete Data URL before sending
    let activeRef = referenceImage
    if (activeRef && !activeRef.startsWith('data:')) {
      try {
        const resolved = await urlToDataUrl(activeRef)
        if (resolved) {
          activeRef = resolved
          setReferenceImage(resolved)
        }
      } catch (err) {
        console.warn('Could not resolve reference image to data URL:', err)
      }
    }

    const CONCURRENCY = effectiveConcurrency
    const initialRemaining = Math.ceil(targets.length / CONCURRENCY) * estSecsPerRound
    setProgress({ done: 0, total: targets.length, currentLabel: targets[0].label, estRemainingSecs: initialRemaining })

    const backend = createImageBackend({ openMayhemApiKey, imageBackend, imageBackendBaseUrl, imageBackendUsername, imageBackendPassword, imageBackendModel })
    const succeeded: string[] = []
    const failed: string[] = []

    let nextIndex = 0
    let completedCount = 0
    const activeLabels = new Set<string>()

    const updateUI = () => {
      const elapsed = (Date.now() - startTimeRef.current) / 1000
      const currentLabel = Array.from(activeLabels).join(', ') || null
      const avgRound = completedCount > 0 ? (elapsed / completedCount) * CONCURRENCY : estSecsPerRound
      const remainingTasks = targets.length - completedCount
      const estRemainingSecs = Math.max(0, Math.ceil(remainingTasks / CONCURRENCY) * avgRound)
      setProgress({
        done: completedCount,
        total: targets.length,
        currentLabel,
        estRemainingSecs,
      })
    }

    const worker = async () => {
      while (true) {
        if (stopRef.current) break
        const i = nextIndex++
        if (i >= targets.length) break
        const exp = targets[i]
        activeLabels.add(exp.label)
        updateUI()

        try {
          const charLead = characterName ? `character ${characterName}` : 'character'
          const emotionPose = EMOTION_POSE_MAP[exp.id.toLowerCase()] || `${exp.label.toLowerCase()} facial expression, with upper body posture and hand gestures matching the emotion, elbows and hands kept fully inside frame borders`
          const isGptModel = imageBackend === 'singularity' || (imageBackend as string) === 'chatgpt-image'
          const backgroundSpec = isGptModel
            ? `[BACKGROUND & TRANSPARENCY - MANDATORY]:
Completely transparent background. Isolated character sprite on a clean transparent background. PNG format with alpha transparency channel behind the character. Absolutely NO solid background color, NO green screen, NO white box, NO backdrop, NO scenery, and NO studio shadows.`
            : `Solid bright neon green background, flat plain backdrop, centered vertical framing.`

          const fullPrompt = activeRef
            ? `Visual novel character sprite of the character in the attached reference image.

[OUTFIT & CLOTHING LOCK - MANDATORY]:
The character MUST wear the EXACT SAME dress and clothing shown in the reference image. Perfectly replicate the identical outfit design, neckline, collar, straps, sleeves, colors, patterns, and fabric accessories 1:1. Absolutely DO NOT change, alter, or redesign the dress. The clothing must remain 100% consistent and identical across all expressions.

[ASPECT RATIO & COMPOSITION - MANDATORY 2:3]:
Aspect ratio: strictly 2:3 vertical portrait format (tall 2:3 ratio).
Vertical upper-body portrait framed from mid-chest/torso upward, centered. Wide framing: BOTH full shoulders, deltoids, and collarbones MUST be completely visible inside the canvas with comfortable margins on the left and right edges. CRITICAL: Any raised hands, wrists, arms, and elbows MUST remain 100% completely inside the image canvas borders without any cutoff or clipping at the edges. Maintain generous headroom and padding above the head and beside shoulders.

[ART STYLE FIDELITY & ZERO NOISE / ZERO GRAIN - MANDATORY]:
Faithfully replicate the EXACT art style of the reference image: match the artist's specific character aesthetic, line art style, eye drawing technique, hair coloring, and palette 1:1.
CRITICAL RENDERING QUALITY: The image MUST be crystal clean, sharp, and completely free of any noise, film grain, digital speckles, stippling, dithering, or gritty texture. Crisp, clean solid 2D digital rendering. Absolutely NO noisy grain, NO grainy filters, NO film grain overlays, and NO stippled noise. Maintain clean defined line art and clean flat/cel shading matching the reference image. No blurry gradient airbrushing, and no 3D CGI plastic rendering.

[EXPRESSION & POSE]:
Expression and pose: ${emotionPose}${basePrompt.trim() ? `. Additional details: ${basePrompt.trim()}` : ''}.

${backgroundSpec}`
            : `Visual novel character sprite of ${charLead}.

[ASPECT RATIO & COMPOSITION - MANDATORY 2:3]:
Aspect ratio: strictly 2:3 vertical portrait format (tall 2:3 ratio).
Vertical upper-body portrait framed from mid-chest/torso upward, centered. Wide framing: BOTH full shoulders, deltoids, and collarbones MUST be completely visible inside the canvas with comfortable margins on the left and right edges. CRITICAL: Any raised hands, wrists, arms, and elbows MUST remain 100% completely inside the image canvas borders without any cutoff or clipping at the edges. Maintain generous headroom and padding above the head and beside shoulders.

[ART STYLE & ZERO NOISE / ZERO GRAIN]:
Crisp 2D illustration, clean defined line art, smooth cel shading, vibrant solid colors. Completely clean digital finish with ZERO noise, ZERO film grain, and ZERO gritty textures. Absolutely NO 3D CGI plastic rendering, NO digital airbrushing, NO blurry gradient smoothing.

[EXPRESSION & POSE]:
Expression and pose: ${emotionPose}${basePrompt.trim() ? `. Additional details: ${basePrompt.trim()}` : ''}.

${backgroundSpec}`

          const result = await backend.generateImage({
            prompt: fullPrompt,
            referenceImage: activeRef || undefined,
            transparent: true,
            width: 512,
            height: 768,
            steps: 20,
            cfgScale: 7,
            model: imageBackendModel || (imageBackend === 'singularity' ? 'gemini-3.8-flash' : 'nano-banana-2'),
          }, controller.signal)
          controller.signal.throwIfAborted()
          if (!result.base64) throw new Error('The backend returned no image data.')
          onGenerated(exp.id, `data:${result.mimeType || 'image/png'};base64,${result.base64}`)
          succeeded.push(exp.label)
        } catch (e) {
          if (!(e instanceof DOMException && e.name === 'AbortError')) failed.push(`${exp.label} (${errorMessage(e)})`)
        } finally {
          activeLabels.delete(exp.label)
          completedCount++
          updateUI()
        }
      }
    }

    const workers = Array.from({ length: Math.min(CONCURRENCY, targets.length) }, () => worker())
    await Promise.all(workers)

    setResults({ succeeded, failed })
    setBusy(false)
  }

  return (
    <Modal
      onClose={onClose}
      title="Generate Expressions"
      size="lg"
      scrollable
    >
      <div className="flex-1 overflow-y-auto space-y-3.5">
        {/* Drag & Drop Portrait Area */}
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`relative flex items-center gap-3.5 rounded-xl border-2 border-dashed p-3 transition-all ${
            isDragging
              ? 'border-accent bg-accent/10 ring-2 ring-accent/30'
              : referenceImage
                ? 'border-border/80 bg-bg-sunken hover:border-accent/40'
                : 'border-border/80 bg-bg-sunken hover:border-accent/40'
          }`}
        >
          {referenceImage ? (
            <>
              <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-lg border border-border/80 bg-bg-elevated shadow-sm">
                <img src={referenceImage} alt="Portrait reference" className="h-full w-full object-cover" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-text truncate">
                  <span>{characterName ? `${characterName}'s Portrait Reference` : 'Portrait Reference'}</span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                    <CheckCircle2 size={10} /> Style & Identity Locked
                  </span>
                </div>
                <p className="text-[11px] text-text-muted mt-0.5">
                  Drag & drop image here or use controls to change
                </p>
                <div className="flex items-center gap-2.5 mt-1">
                  <label className="cursor-pointer text-[11px] font-medium text-accent hover:underline">
                    Change image
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                    />
                  </label>
                  {characterPortrait && referenceImage !== characterPortrait && (
                    <button
                      type="button"
                      className="text-[11px] text-text-muted hover:text-text hover:underline"
                      onClick={() => setReferenceImage(characterPortrait)}
                    >
                      Reset to Avatar
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-[11px] text-danger/80 hover:text-danger hover:underline"
                    onClick={() => setReferenceImage('')}
                  >
                    Remove
                  </button>
                </div>
              </div>
            </>
          ) : (
            <label className="flex w-full cursor-pointer items-center justify-center gap-3 py-2 text-text-muted hover:text-text">
              <Upload size={18} className="text-accent shrink-0" />
              <div className="text-left">
                <p className="text-xs font-medium text-text">Drag & drop character portrait, or click to upload</p>
                <p className="text-[11px] text-text-muted">PNG, JPG, WEBP</p>
              </div>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
            </label>
          )}
        </div>

        {/* Optional prompt field */}
        <div>
          <label className="block text-xs font-medium text-text mb-1">
            {referenceImage ? 'Style / outfit prompt (optional)' : 'Appearance prompt'}
          </label>
          <input
            type="text"
            value={basePrompt}
            onChange={(e) => setBasePrompt(e.target.value)}
            placeholder={referenceImage ? 'Optional: e.g. casual clothes, blushing' : 'e.g. dark purple twintails, black school blazer'}
            className="w-full rounded-xl bg-bg-sunken px-3 py-2 text-xs text-text outline-none ring-1 ring-transparent transition-shadow focus:ring-accent/40 placeholder:text-text-muted/50"
          />
        </div>

        {/* Parallel Streams Selector for ChatGPT Account Pool */}
        {(imageBackend === 'singularity' || (imageBackend as string) === 'chatgpt-image') && (
          <div className="flex items-center justify-between rounded-xl bg-bg-sunken/60 px-3 py-2 border border-border/40">
            <div className="flex items-center gap-1.5">
              <Sparkles size={13} className="text-accent" />
              <div>
                <span className="text-xs font-medium text-text">Parallel Processing</span>
                <span className="ml-1.5 text-[10px] text-text-muted">(7 accounts pool)</span>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {[1, 2, 3, 4, 7].map((num) => (
                <button
                  key={num}
                  type="button"
                  disabled={busy}
                  onClick={() => setConcurrency(num)}
                  className={`rounded-lg px-2 py-0.5 text-xs font-medium transition-colors ${
                    concurrency === num
                      ? 'bg-accent text-accent-fg shadow-sm'
                      : 'bg-bg-elevated text-text-muted hover:text-text hover:bg-bg-subtle'
                  }`}
                >
                  {num === 7 ? '7x (Max)' : `${num}x`}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Expressions selection */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-text">Expressions ({selected.size})</span>
              {selected.size > 0 && (
                <span className="inline-flex items-center gap-1 rounded-md bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">
                  <Clock size={11} />
                  ~{formatDuration(initialEstTotalSecs)}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <button type="button" className="text-xs text-accent hover:underline" onClick={() => setSelected(new Set(expressions.map((e) => e.id)))}>
                Select all
              </button>
              <button type="button" className="text-xs text-accent hover:underline" onClick={() => setSelected(new Set())}>
                Select none
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {expressions.map((exp) => (
              <Chip key={exp.id} on={selected.has(exp.id)} onClick={() => toggle(exp.id)} disabled={busy}>
                {exp.label}
                {exp.hasSprite && ' •'}
              </Chip>
            ))}
          </div>
        </div>

        {busy && (
          <div className="rounded-xl border border-accent/20 bg-bg-elevated p-3.5 text-sm shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div className="truncate">
                <span className="font-medium text-text">
                  Generating {progress.currentLabel}
                </span>
                <span className="ml-1 text-xs text-text-muted">
                  ({progress.done + 1}/{progress.total})
                </span>
              </div>
              <div className="flex items-center gap-2">
                {progress.estRemainingSecs !== null && (
                  <span className="text-xs text-accent font-medium flex items-center gap-1">
                    <Clock size={12} />
                    ~{formatDuration(progress.estRemainingSecs)} left
                  </span>
                )}
                <Button
                  variant="ghost"
                  className="!py-1 !px-2.5 !text-xs"
                  onClick={() => {
                    stopRef.current = true
                    controllerRef.current?.abort()
                    setStopRequested(true)
                  }}
                  disabled={stopRequested}
                >
                  {stopRequested ? 'Stopping…' : 'Stop'}
                </Button>
              </div>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-sunken">
              <div className="h-full bg-accent transition-all duration-300" style={{ width: `${(progress.done / Math.max(1, progress.total)) * 100}%` }} />
            </div>
          </div>
        )}

        {results && (
          <div className="rounded-xl bg-bg-elevated p-3 text-xs">
            {results.succeeded.length > 0 && <p className="text-text font-medium">✓ Generated ({results.succeeded.length}): {results.succeeded.join(', ')}</p>}
            {results.failed.length > 0 && <p className="mt-1 text-danger">Failed ({results.failed.length}): {results.failed.join('; ')}</p>}
          </div>
        )}
      </div>

      <div className="mt-4 flex shrink-0 justify-between items-center border-t border-border/50 pt-3">
        <div className="text-xs text-text-muted">
          {selected.size > 0 && !busy && (
            <span>Est: <strong>~{formatDuration(initialEstTotalSecs)}</strong></span>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose}>
            {results ? 'Close' : 'Cancel'}
          </Button>
          {!results && (
            <Button variant="primary" onClick={generate} disabled={!canGenerate}>
              {busy ? 'Generating…' : `Generate ${selected.size} Expressions`}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}


