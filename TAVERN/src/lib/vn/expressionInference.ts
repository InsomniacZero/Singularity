/**
 * Fast, deterministic emotion inference from roleplay narrative text and dialogue.
 * When an LLM omits the <<scene:expression=...>> tag or lazily defaults to 'neutral',
 * this accurately extracts the character's live emotional reaction from their actions,
 * gestures, vocalizations, and expressions in the prose.
 */

interface EmotionRule {
  id: string
  // RegEx pattern matching dialogue/narration action beats
  pattern: RegExp
  // Priority weight (higher wins on tie)
  priority: number
}

const EMOTION_RULES: EmotionRule[] = [
  // Laughter / Amusement
  {
    id: 'laughing',
    pattern:
      /\b(laugh(s|ed|ing)?|sharp laugh|giggle(s|d|ing)?|chuckle(s|d|ing)?|snicker(s|d|ing)?|cackle(s|d|ing)?|bursts? out laughing|howling with laughter|cracking up|chortl(e|es|ed|ing))\b/i,
    priority: 10,
  },
  // Smirk / Playful Grin / Teasing / Amused
  {
    id: 'smirk',
    pattern:
      /\b(smirk(s|ed|ing)?|playful grin|crooked grin|sly smile|sly grin|wicked grin|mischievous grin|smug(ly|ness)?|wry grin|wry smile|cocky grin|half-smile|amused(ly)?|amused smile|amused grin|amused expression|amusement|teasing(ly)? smile)\b/i,
    priority: 9,
  },
  // Happy / Cheerful Smile
  {
    id: 'happy',
    pattern:
      /\b(smile(s|d|ing)?|smiling|beam(s|ed|ing)?|bright smile|cheerful(ly)?|grin(s|ned|ning)?|radiant|broad grin|warm smile)\b/i,
    priority: 7,
  },
  // Annoyed / Irritated
  {
    id: 'annoyed',
    pattern:
      /\b(annoy(ed|ing|ance)?|irritat(ed|ing|ion)?|scowl(s|ed|ing)?|furrows? (her|his|their)? brow|rolls? (her|his|their)? eyes|huff(s|ed|ing)?|pout(s|ed|ing)?|crosses? (her|his|their)? arms|grunts?|irked|clicks? (her|his|their)? tongue|tsks?)\b/i,
    priority: 8,
  },
  // Angry / Furious
  {
    id: 'angry',
    pattern:
      /\b(angry|angrily|furious(ly)?|glare(s|d|ing)?|snarl(s|ed|ing)?|growl(s|ed|ing)?|clenche(s|d)? (her|his|their)? (fists?|jaw)|teeth grinding|snaps? angrily|rage|yell(s|ed|ing)?|seething|fuming)\b/i,
    priority: 10,
  },
  // Surprised / Shocked
  {
    id: 'surprised',
    pattern:
      /\b(surprise(d|s)?|gasp(s|ed|ing)?|eyes widen(ed)?|taken aback|shock(ed|ing)?|startle(d|s)?|jaw drops?|blinks in surprise|dumbfounded|flabbergasted)\b/i,
    priority: 9,
  },
  // Blush / Flustered
  {
    id: 'blush',
    pattern:
      /\b(blush(es|ed|ing)?|cheeks? (turn(ed)?|flush(ed)?|burn(ing)?|glow(ing)? red|crimson)|flustered|bright red face|flushes?|rosy cheeks)\b/i,
    priority: 9,
  },
  // Embarrassed / Sheepish
  {
    id: 'embarrassed',
    pattern:
      /\b(embarrass(ed|ing|ment)?|mortified|covers? (her|his|their)? face|looks? away sheepishly|hides? (her|his|their)? (face|eyes)|stammers?|sheepish(ly)?)\b/i,
    priority: 8,
  },
  // Flirty / Winking / Alluring
  {
    id: 'flirty',
    pattern:
      /\b(wink(s|ed|ing)?|flirt(s|ed|ing|atious)?|teasingly|coquettish(ly)?|twirls? (her|his|their)? hair|seductively|flutter(s|ed)? (her|his|their)? eyelashes)\b/i,
    priority: 8,
  },
  // Crying / Tears
  {
    id: 'crying',
    pattern:
      /\b(cry(ing|ies|ied)?|weep(s|ing)?|sob(s|bed|bing)?|tears? (streaming|welling|falling)|teary-eyed|wipe(s|d)? away tears?|sniffl(e|es|ed|ing))\b/i,
    priority: 10,
  },
  // Sad / Melancholic
  {
    id: 'sad',
    pattern:
      /\b(sad(ly|ness)?|melanchol(y|ic)|downcast|frown(s|ed|ing)?|sighs? sadly|looking down sadly|sorrow(ful)?|crestfallen|heartbroken|dejected)\b/i,
    priority: 7,
  },
  // Confused / Puzzled
  {
    id: 'confusion',
    pattern:
      /\b(confus(ed|ing|ion)?|puzzl(ed|ing)?|perplex(ed|ing)?|quizzical(ly)?|tilts? (her|his|their)? head|blinks? in confusion|bewildered|baffled)\b/i,
    priority: 7,
  },
  // Scared / Frightened
  {
    id: 'scared',
    pattern:
      /\b(scared?|fear(ful)?|trembl(es|ed|ing)|shiver(s|ed|ing) in fear|frighten(ed)?|panick(ed|y)?|shrinks? back|cowering|terrified)\b/i,
    priority: 9,
  },
  // Relief
  {
    id: 'relief',
    pattern:
      /\b(sigh(s|ed|ing)? in relief|breathes? a sigh of relief|shoulders? (drop|relax|sag) in relief|relieved|exhale(s|d)? softly)\b/i,
    priority: 8,
  },
  // Pain / Wincing
  {
    id: 'pain',
    pattern:
      /\b(wince(s|d|ing)?|groan(s|ed|ing)? in pain|grimace(s|d|ing)?|clutche(s|d)? (her|his|their)? (chest|arm|wound)|aches?|hurts?)\b/i,
    priority: 8,
  },
  // Thinking / Pensive / Contemplative
  {
    id: 'thinking',
    pattern:
      /\b(think(s|ing)?|ponder(s|ed|ing)?|musing|finger on (her|his|their)? chin|contemplat(es?|ed|ing)?|lost in thought|weighing|looks? out (the|a|her|his|their)? window|gaz(es?|ed|ing) (out|away|thoughtfully|wistfully|into the distance|at the cherry|at the trees|at the)|thoughtful(ly)?|pensive(ly)?|asks? (softly|quietly|earnestly|sincerely|gently|tentatively)|eyes soften(ed)?|tone (softens|turns? serious|quiets?|drops?)|serious(ly)?|in all seriousness|sober(ly)?|hesitat(es?|ed|ing)|pause(s|d)?\b.{0,25}\b(before|looking|gazing|asking)|can i ask you something)\b/i,
    priority: 7,
  },
  // Neutral / Calm / Quiet
  {
    id: 'neutral',
    pattern:
      /\b(calm(ly)?|matter-of-fact(ly)?|composed|collects? (her|his|their)? thoughts|resumes? a neutral expression|face (softens|relaxes|clears)|blank expression|straight face|in a quiet note|in a quieter tone|quiet note|quietly asks?)\b/i,
    priority: 5,
  },
  // Determined / Resolute
  {
    id: 'determined',
    pattern:
      /\b(determin(ed|ation)?|resolute|nods? firmly|steels? (her|his|their)? (resolve|gaze)|fist clenched firmly|jaw sets?|steely gaze)\b/i,
    priority: 7,
  },
  // Sleepy / Tired / Yawning
  {
    id: 'sleepy',
    pattern:
      /\b(yawn(s|ed|ing)?|drowsy|sleepy|half-asleep|rubs? (her|his|their)? eyes|drooping (eyelids?|eyes)|exhausted)\b/i,
    priority: 7,
  },
  // Disgust / Repulsed
  {
    id: 'disgust',
    pattern:
      /\b(disgust(ed)?|repulsed?|curls? (her|his|their)? lip in disgust|nauseated|grossed out|recoils? in revulsion|sneers?)\b/i,
    priority: 8,
  },
  // Yearning / Longing / Wistful
  {
    id: 'yearning',
    pattern:
      /\b(yearn(s|ing)?|longing(ly)?|reaches? (her|his|their)? hand out toward|pleading (gaze|eyes)|wistful(ly)?|distant gaze|wistful smile)\b/i,
    priority: 8,
  },
  // Love / Romantic Tender
  {
    id: 'love',
    pattern:
      /\b(loving(ly)?|gaze(s)? (softly|tenderly) with deep love|tenderly whispers?|eyes full of love|gazes adoringly)\b/i,
    priority: 9,
  },
  // Smitten / Starry-eyed
  {
    id: 'smitten',
    pattern:
      /\b(smitten|starry-eyed|gazing dreamily|enamored|completely captivated|dazed with affection)\b/i,
    priority: 9,
  },
  // Sultry / Seductive
  {
    id: 'sultry',
    pattern:
      /\b(sultry|bedroom eyes|seductive gaze|bites? (her|his|their)? lip seductively|half-lidded gaze|sensual(ly)?)\b/i,
    priority: 9,
  },
  // Aroused / Heavy breath
  {
    id: 'aroused',
    pattern:
      /\b(aroused?|heavy (breathing|breath)|breath(es)? heavily|shiver(s)? with desire|flush(ed)? with heat|quiver(s)? with want)\b/i,
    priority: 10,
  },
]

/**
 * Infers the closest matching expression ID from the message text if the model omitted a tag
 * or defaulted to 'neutral' while clearly depicting a concrete emotion in prose.
 */
export function inferExpressionFromText(
  text: string,
  allowedExpressionIds: string[],
): string | null {
  if (!text.trim()) return null
  const allowed = new Set(allowedExpressionIds)
  if (allowed.size === 0) return null

  let bestId: string | null = null
  let bestPriority = -1
  let earliestIndex = Infinity

  for (const rule of EMOTION_RULES) {
    if (!allowed.has(rule.id)) continue
    const match = rule.pattern.exec(text)
    if (match) {
      // Prioritize higher-weight emotions, breaking ties by what appeared earlier in the turn
      if (rule.priority > bestPriority || (rule.priority === bestPriority && match.index < earliestIndex)) {
        bestId = rule.id
        bestPriority = rule.priority
        earliestIndex = match.index
      }
    }
  }

  return bestId
}

export interface ExpressionBeat {
  expression: string
  charIndex: number
  wordIndex: number
  source: 'tag' | 'inference'
}

/**
 * Extracts an ordered progression of emotional beats with character/word positions across
 * a single response. Enables VN sprites and reactive portraits to transition dynamically
 * as the reader reads through paragraphs with multiple emotional beats.
 */
export function extractExpressionTimeline(
  text: string,
  allowedExpressionIds: string[],
  initialTaggedExpression?: string,
): ExpressionBeat[] {
  if (!text.trim()) {
    return initialTaggedExpression
      ? [{ expression: initialTaggedExpression, charIndex: 0, wordIndex: 0, source: 'tag' }]
      : []
  }

  const allowed = new Set(
    allowedExpressionIds.length > 0 ? allowedExpressionIds : ['neutral', 'happy', 'smirk', 'thinking', 'sad']
  )

  const beats: ExpressionBeat[] = []

  // Helper to count words up to a character index
  const countWordsUpTo = (idx: number): number => {
    const sub = text.slice(0, idx).trim()
    if (!sub) return 0
    return sub.split(/\s+/).length
  }

  // 1. Check for explicit mid-text tags: <<scene:expression=...>> or <expression:...>
  const tagRegex = /<{1,2}(?:scene:.*?\bexpression=|expression:)([a-zA-Z0-9_-]+)[^>]*>{1,2}/gi
  let tagMatch: RegExpExecArray | null
  const explicitTags: { expression: string; index: number }[] = []
  while ((tagMatch = tagRegex.exec(text)) !== null) {
    const exp = tagMatch[1].toLowerCase().trim()
    if (allowed.has(exp)) {
      explicitTags.push({ expression: exp, index: tagMatch.index })
    }
  }

  if (explicitTags.length > 1) {
    for (const tag of explicitTags) {
      if (beats.length === 0 || beats[beats.length - 1].expression !== tag.expression) {
        beats.push({
          expression: tag.expression,
          charIndex: tag.index,
          wordIndex: countWordsUpTo(tag.index),
          source: 'tag',
        })
      }
    }
    return beats
  }

  // 2. Prose inference: Analyze emotional trajectory across paragraphs and dialogue turns
  let startingExp = initialTaggedExpression && allowed.has(initialTaggedExpression)
    ? initialTaggedExpression
    : null

  const paragraphs = text.split(/\n\n+/)
  if (!startingExp || startingExp === 'neutral') {
    const firstParaInferred = inferExpressionFromText(paragraphs[0] || text, Array.from(allowed))
    if (firstParaInferred) {
      startingExp = firstParaInferred
    } else if (!startingExp) {
      startingExp = 'neutral'
    }
  }

  beats.push({
    expression: startingExp,
    charIndex: 0,
    wordIndex: 0,
    source: initialTaggedExpression ? 'tag' : 'inference',
  })

  let currentCharOffset = 0
  let currentActiveExp = startingExp
  const MIN_WORD_GAP = 12

  for (let p = 0; p < paragraphs.length; p++) {
    const para = paragraphs[p]
    const paraCharStart = text.indexOf(para, currentCharOffset)
    const effectiveCharStart = paraCharStart !== -1 ? paraCharStart : currentCharOffset
    currentCharOffset = effectiveCharStart + para.length

    // Don't duplicate inference on the first paragraph if it already set the initial beat
    if (p === 0 && startingExp !== 'neutral') {
      continue
    }

    let bestParaExp: string | null = null
    let bestParaPriority = -1
    let bestParaIndex = 0

    for (const rule of EMOTION_RULES) {
      if (!allowed.has(rule.id)) continue
      const m = rule.pattern.exec(para)
      if (m) {
        if (rule.priority > bestParaPriority) {
          bestParaExp = rule.id
          bestParaPriority = rule.priority
          bestParaIndex = m.index
        }
      }
    }

    if (bestParaExp && bestParaExp !== currentActiveExp) {
      const matchCharIndex = effectiveCharStart + bestParaIndex
      const wordIdx = countWordsUpTo(matchCharIndex)
      const lastBeat = beats[beats.length - 1]

      if (wordIdx - lastBeat.wordIndex >= MIN_WORD_GAP) {
        beats.push({
          expression: bestParaExp,
          charIndex: matchCharIndex,
          wordIndex: wordIdx,
          source: 'inference',
        })
        currentActiveExp = bestParaExp
      }
    }
  }

  return beats
}
