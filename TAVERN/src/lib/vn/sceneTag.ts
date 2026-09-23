/**
 * Parses/emits the `<<scene:...>>` directive the model appends to a reply to drive VN mode's
 * expression/background/mood/outfit, and strips it from what's shown mid-stream.
 */

import type { ExpressionBeat } from '@/lib/vn/expressionInference'

export interface SceneTag {
  expression?: string
  background?: string
  /** Ambient scene mood (src/lib/vn/moods.ts) — selects the background-music track in VN mode. */
  mood?: string
  /** Wardrobe state (src/lib/vn/outfits.ts). Unset means "no change", not "base outfit". */
  outfit?: string
  /** Sequence of emotional shifts within a single response for dynamic sprite progression */
  expressionTimeline?: ExpressionBeat[]
}

const TAG_PREFIX = '<<scene:'
// Global match, not anchored to end-of-string: a model can emit a tag mid-reply then another at the
// end, and anchoring to `$` would leave the first as literal unstripped text.
const TAG_RE = /\n?<{1,2}scene:([^>]*)>{1,2}/gi

/** Pulls every `<<scene:...>>` directive out of a completed generation, using the LAST one for the actual metadata while stripping ALL of them from the returned text. */
export function extractSceneTag(raw: string): { text: string; scene?: SceneTag } {
  let lastMatch: RegExpMatchArray | undefined
  for (const match of raw.matchAll(TAG_RE)) lastMatch = match
  const scene: SceneTag = {}
  if (lastMatch && lastMatch[1]) {
    for (const pair of lastMatch[1].split(',')) {
      const [key, value] = pair.split('=').map((s) => s.trim().toLowerCase())
      if (key === 'expression' && value) scene.expression = value
      if (key === 'background' && value) scene.background = value
      if (key === 'mood' && value) scene.mood = value
      if (key === 'outfit' && value) scene.outfit = value
    }
  }
  let text = raw.replace(TAG_RE, '')
  text = stripSceneTagForDisplay(text).trim()
  return { text, scene: Object.keys(scene).length ? scene : undefined }
}

/** Hides an in-progress (or just-completed) scene tag from what's shown mid-stream, so it never flashes as visible dialogue. */
export function stripSceneTagForDisplay(text: string): string {
  let clean = text.replace(/\n?<{1,2}scene:[^>]*>{1,2}/gi, '')
  const sceneIdx = clean.toLowerCase().lastIndexOf('<scene:')
  const dblIdx = clean.lastIndexOf('<<')
  let idx = -1
  if (dblIdx !== -1 && (sceneIdx === -1 || dblIdx <= sceneIdx)) {
    idx = dblIdx
  } else if (sceneIdx !== -1) {
    idx = sceneIdx
  }
  if (idx !== -1) {
    const tail = clean.slice(idx).toLowerCase()
    if ('<<scene:'.startsWith(tail) || tail.startsWith('<<scene:') || '<scene:'.startsWith(tail) || tail.startsWith('<scene:')) {
      clean = clean.slice(0, idx)
    }
  } else if (clean.endsWith('<')) {
    clean = clean.slice(0, -1)
  }
  return clean.replace(/\s+$/, '')
}

/** Extracts any scene tag attributes (especially background) even from incomplete/early streaming chunks. */
export function extractEarlySceneTag(text: string): SceneTag | undefined {
  const match = text.match(/<{1,2}scene:([^>]*)>{0,2}/i)
  if (!match || !match[1]) return undefined
  const scene: SceneTag = {}
  for (const pair of match[1].split(',')) {
    const [key, value] = pair.split('=').map((s) => s.trim().toLowerCase())
    if (!key || !value) continue
    if (key === 'expression') scene.expression = value
    if (key === 'background') scene.background = value
    if (key === 'mood') scene.mood = value
    if (key === 'outfit') scene.outfit = value
  }
  return Object.keys(scene).length ? scene : undefined
}

/** Instructs the model to tag each reply with the closest-matching expression/background/mood, so VN mode can react to it. */
export function buildSceneInstruction(options?: {
  expressionIds: string[]
  backgroundIds: string[]
  /** Passed only when the world actually has music. */
  moodIds?: string[]
  /** Passed only when the character has more than one selectable wardrobe state — see `selectableOutfitIds` in `outfits.ts`. */
  outfitIds?: string[]
  /** What the character is wearing right now, so the model knows what it would be *changing from*. */
  currentOutfitId?: string
}): string {
  if (!options) return ''
  const wantsMood = !!options.moodIds && options.moodIds.length > 0
  // Nothing worth asking for. Mood counts on its own: outside Visual Novel mode it is the only
  // field anything still reads (it picks the background music), so a mood-only request is valid.
  if (options.expressionIds.length === 0 && options.backgroundIds.length === 0 && !wantsMood) return ''
  // One id is no choice at all (it's always just the base outfit), so it isn't worth a field.
  const wantsOutfit = !!options.outfitIds && options.outfitIds.length > 1
  // Only the fields actually being asked for appear in the format line — a mood-only request must
  // not still show `expression=ID` in the template it tells the model to follow.
  const fields = [
    options.expressionIds.length ? 'expression=ID' : '',
    options.backgroundIds.length ? 'background=ID' : '',
    wantsMood ? 'mood=ID' : '',
    wantsOutfit ? 'outfit=ID' : '',
  ].filter(Boolean)
  const format = `<<scene:${fields.join(',')}>>`
  return [
    'At the very start or end of your in-character reply, include exactly one line in this exact format. This line is metadata only: never mention or explain it in the dialogue.',
    format,
    options.expressionIds.length ? `Valid expression IDs: ${options.expressionIds.join(', ')}` : '',
    options.backgroundIds.length ? `Valid background IDs: ${options.backgroundIds.join(', ')}` : '',
    wantsMood ? `Valid mood IDs: ${options.moodIds!.join(', ')}` : '',
    wantsOutfit ? `Valid outfit IDs: ${options.outfitIds!.join(', ')}` : '',
    wantsOutfit
      ? `The character is currently wearing "${options.currentOutfitId || 'base'}". Only use a different outfit ID when the story has actually changed what they are wearing — they got changed, arrived somewhere needing different clothes, undressed. Otherwise repeat the current one. Never change an outfit just because the mood shifted.`
      : '',
    options.expressionIds.length || options.backgroundIds.length
      ? wantsMood
        ? "Pick whichever IDs best match the character's emotion, the current setting, and the overall feeling of the scene."
        : "Pick whichever IDs best match the character's emotion and the current setting."
      : 'Pick whichever ID best matches the overall feeling of the scene.',
  ]
    .filter(Boolean)
    .join('\n')
}
