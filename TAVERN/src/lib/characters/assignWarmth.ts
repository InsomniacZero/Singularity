import type { ChatBackend } from '@/lib/api/chatBackend'
import { generateWithTimeout } from '@/lib/api/generateWithTimeout'
import { parseLenientJson } from '@/lib/jsonRepair'
import type { CharacterCardData } from './cardSpec'

export interface ExpressionItem {
  id: string
  label: string
}

export interface WarmthAssignmentResult {
  unlocks: Record<string, number>
  archetypeSummary: string
  method: 'ai' | 'heuristic'
}

/**
 * Detects core personality archetypes and emotional tendencies from character text.
 */
export function detectPersonalityTraits(text: string): {
  isTsundere: boolean
  isKuudere: boolean
  isDandere: boolean
  isGenki: boolean
  isSeductive: boolean
  isYandere: boolean
  isSadistic: boolean
  isMaidPolite: boolean
  archetypeTitle: string
} {
  const t = text.toLowerCase()

  const isTsundere =
    /\b(tsundere|prickly|feisty|hostile at first|baka|idiot|calls (you|{{user}}) idiot|defensive|harsh exterior|soft interior|denies feelings|denies liking|secretly soft|stubbornly denies)\b/i.test(
      t,
    )
  const isKuudere =
    /\b(kuudere|stoic|aloof|emotionless|expressionless|monotone|deadpan|quiet|detached|unflinching|cold exterior|rarely smiles|serious|unemotional|indifferent)\b/i.test(
      t,
    )
  const isDandere =
    /\b(dandere|shy|timid|nervous|stutters|submissive|introvert|fidgets|blushes easily|anxious|docile|meek|soft-spoken|hesitant)\b/i.test(
      t,
    )
  const isGenki =
    /\b(genki|bubbly|cheerful|energetic|hyper|outgoing|sunny|sweet|friendly|optimistic|peppy|extrovert|lively|radiant|always smiling)\b/i.test(
      t,
    )
  const isSeductive =
    /\b(seductive|flirty|teasing|succubus|gyaru|carnal|sensual|femme fatale|coquettish|playful|alluring|provocative|smug|vixen|erotic)\b/i.test(
      t,
    )
  const isYandere =
    /\b(yandere|obsessive|possessive|stalker|clingy|lovesick|unhinged|delusional|manic|overly attached|mine alone)\b/i.test(
      t,
    )
  const isSadistic =
    /\b(sadistic|dominant|arrogant|queen|ojou|haughty|condescending|cruel|domme|mistress|brat|superiority)\b/i.test(
      t,
    )
  const isMaidPolite =
    /\b(maid|butler|servant|polite|formal|obedient|loyal|respectful|courteous|dutiful|service)\b/i.test(
      t,
    )

  const titles: string[] = []
  if (isTsundere) titles.push('Tsundere (Guarded & Prickly)')
  if (isKuudere) titles.push('Kuudere (Stoic & Aloof)')
  if (isDandere) titles.push('Dandere (Shy & Timid)')
  if (isGenki) titles.push('Genki (Bubbly & Cheerful)')
  if (isSeductive) titles.push('Seductive & Teasing')
  if (isYandere) titles.push('Yandere (Obsessive Love)')
  if (isSadistic) titles.push('Sadistic & Dominant')
  if (isMaidPolite) titles.push('Polite & Formal')

  const archetypeTitle = titles.length > 0 ? titles.join(' / ') : 'Balanced Roleplay Persona'

  return {
    isTsundere,
    isKuudere,
    isDandere,
    isGenki,
    isSeductive,
    isYandere,
    isSadistic,
    isMaidPolite,
    archetypeTitle,
  }
}

/**
 * Pure heuristic calculator that assigns nuanced warmth levels (0 to 100) to each expression
 * based on character personality, description, and archetypal defense mechanisms.
 */
export function assignWarmthHeuristic(
  character: {
    name?: string
    personality?: string
    description?: string
    scenario?: string
    mes_example?: string
    system_prompt?: string
  },
  expressions: ExpressionItem[],
): { unlocks: Record<string, number>; archetypeSummary: string } {
  const combinedText = [
    character.name ?? '',
    character.personality ?? '',
    character.description ?? '',
    character.scenario ?? '',
    character.mes_example ?? '',
    character.system_prompt ?? '',
  ].join(' ')

  const traits = detectPersonalityTraits(combinedText)
  const unlocks: Record<string, number> = {}

  for (const exp of expressions) {
    const id = exp.id.toLowerCase()
    const label = exp.label.toLowerCase()

    let score = 0 // default baseline is 0 so conversational expressions work on turn 1

    switch (id) {
      // ─── Standard Conversational / Situational Emotions (Always 0 on Turn 1) ───
      case 'neutral':
      case 'happy':
      case 'smirk':
      case 'laughing':
      case 'angry':
      case 'annoyed':
      case 'surprised':
      case 'confusion':
      case 'thinking':
      case 'determined':
      case 'scared':
      case 'sad':
      case 'disgust':
      case 'sleepy':
      case 'pain':
        score = 0
        break

      // ─── Guarded / Romantic / Intimacy Progression Emotions ───
      case 'relief':
        score = traits.isTsundere || traits.isKuudere ? 10 : 5
        break

      case 'embarrassed':
        if (traits.isDandere) score = 5
        else if (traits.isTsundere) score = 10
        else score = 15
        break

      case 'blush':
        if (traits.isDandere) score = 10 // flusters very quickly
        else if (traits.isTsundere) score = 20 // walls crack as warmth develops
        else if (traits.isKuudere) score = 25 // rare gap-moe
        else if (traits.isSeductive) score = 25 // hard to fluster genuinely
        else score = 15
        break

      case 'flirty':
        if (traits.isSeductive) score = 0 // natural casual mode
        else if (traits.isTsundere || traits.isDandere || traits.isKuudere) score = 25
        else score = 15
        break

      case 'yearning':
        if (traits.isYandere) score = 10
        else if (traits.isDandere) score = 15
        else if (traits.isTsundere || traits.isKuudere) score = 30
        else score = 25
        break

      case 'crying':
        if (traits.isDandere) score = 10
        else if (traits.isTsundere || traits.isKuudere) score = 30 // guarded breakdown
        else score = 20
        break

      case 'love':
        if (traits.isYandere) score = 10
        else if (traits.isTsundere || traits.isKuudere) score = 40
        else score = 30
        break

      case 'smitten':
        if (traits.isYandere) score = 10
        else if (traits.isTsundere || traits.isKuudere) score = 45
        else score = 35
        break

      case 'sultry':
        if (traits.isSeductive) score = 10
        else if (traits.isTsundere || traits.isKuudere) score = 45
        else score = 30
        break

      case 'aroused':
        if (traits.isSeductive) score = 25
        else if (traits.isTsundere || traits.isKuudere) score = 55
        else score = 40
        break

      default: {
        // Custom expression parsing based on semantic keywords
        const term = `${id} ${label}`
        if (/\b(orgasm|horny|naked|intimate|lewd|ecstasy|climax)\b/i.test(term)) {
          score = traits.isSeductive ? 60 : 90
        } else if (/\b(kiss|smooch|cuddle|making out)\b/i.test(term)) {
          score = traits.isSeductive ? 40 : 70
        } else if (/\b(pout|sulking)\b/i.test(term)) {
          score = traits.isTsundere ? 15 : 35
        } else if (/\b(smug|taunt|mocking)\b/i.test(term)) {
          score = traits.isSeductive || traits.isSadistic ? 5 : 25
        } else if (/\b(panic|shock|dizzy|freaking out)\b/i.test(term)) {
          score = traits.isDandere ? 15 : 30
        } else if (/\b(wink|tease|playful)\b/i.test(term)) {
          score = traits.isSeductive ? 5 : 35
        } else if (/\b(scowl|glare|displeased)\b/i.test(term)) {
          score = traits.isTsundere ? 5 : 40
        } else {
          score = 25
        }
        break
      }
    }

    unlocks[exp.id] = Math.max(0, Math.min(100, Math.round(score)))
  }

  return {
    unlocks,
    archetypeSummary: traits.archetypeTitle,
  }
}

/**
 * Assigns warmth thresholds to character expressions.
 * Tries LLM generation first (if client or local Universal-Gift proxy is available),
 * and automatically falls back to intelligent personality heuristic if offline.
 */
export async function assignExpressionWarmth(
  character: CharacterCardData,
  expressions: ExpressionItem[],
  client?: ChatBackend | null,
): Promise<WarmthAssignmentResult> {
  const combinedText = [
    character.name,
    character.personality,
    character.description,
    character.scenario,
  ]
    .filter(Boolean)
    .join('\n')

  // 1. If backend client is provided, attempt AI evaluation with a strict timeout
  if (client && combinedText.trim().length > 10) {
    try {
      const expList = expressions.map((e) => `"${e.id}" (${e.label})`).join(', ')
      const prompt = [
        'You are an expert visual novel narrative designer. In this game, each character expression has an "Unlock Warmth" number from 0 to 100.',
        'Warmth represents relationship intimacy with {{user}}:',
        '- 0: Strangers / baseline persona (all standard conversational and situational expressions).',
        '- 10-25: Developing rapport / first sweet blushes and flustered reactions.',
        '- 26-40: Deepening bond / romantic yearning, tears, open loving smiles.',
        '- 41-60: Intimate romance / smitten, sultry, and passionate arousal.',
        '',
        'CRITICAL DESIGN RULES:',
        '1. ALL standard conversational expressions (neutral, happy, smirk, laughing, angry, annoyed, surprised, confusion, thinking, determined, scared, sad, disgust, sleepy, pain) MUST BE SET TO 0. If a user tells a joke on turn 1, the character must be able to laugh!',
        '2. ONLY romantic, flustered, intimate, or deep-vulnerability expressions (blush, embarrassed, flirty, yearning, love, smitten, crying, sultry, aroused) should have warmth thresholds above 0 (typically 10 to 50 based on their personality and archetypal defenses).',
        '',
        `Character Name: ${character.name}`,
        character.personality ? `Personality: ${character.personality}` : '',
        character.description ? `Description: ${character.description}` : '',
        character.scenario ? `Scenario: ${character.scenario}` : '',
        '',
        `Expressions to evaluate:\n${expList}`,
        '',
        'Task: Assign an integer warmth threshold (0-100) for every expression based on this character\'s specific personality traits and the rules above.',
        'Output ONLY a valid JSON object mapping each expression ID to its integer warmth number, like {"neutral": 0, "happy": 0, "laughing": 0, "blush": 20, ...}. No markdown fences, no commentary.',
        'JSON:',
      ]
        .filter(Boolean)
        .join('\n')

      const responseText = await generateWithTimeout(
        client,
        {
          prompt,
          max_length: 500,
          max_context_length: await client.getEffectiveMaxContext(),
          temperature: 0.3,
          stop_sequence: ['\n\n\n', '```'],
          trim_stop: true,
        },
        'Assign expression warmth from personality',
      )

      const parsed = parseLenientJson(responseText)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const rawMap = parsed as Record<string, unknown>
        const unlocks: Record<string, number> = {}
        let matchCount = 0

        for (const exp of expressions) {
          if (exp.id in rawMap) {
            const val = Number(rawMap[exp.id])
            if (!Number.isNaN(val)) {
              unlocks[exp.id] = Math.max(0, Math.min(100, Math.round(val)))
              matchCount++
            }
          }
        }

        // If the AI returned numbers for at least half the expressions, fill missing with heuristic
        if (matchCount >= Math.min(expressions.length, 5)) {
          const fallback = assignWarmthHeuristic(character, expressions)
          for (const exp of expressions) {
            if (!(exp.id in unlocks)) {
              unlocks[exp.id] = fallback.unlocks[exp.id] ?? 0
            }
          }
          const traits = detectPersonalityTraits(combinedText)
          return {
            unlocks,
            archetypeSummary: traits.archetypeTitle,
            method: 'ai',
          }
        }
      }
    } catch {
      // Fall through to heuristic on any model error or timeout
    }
  }

  // 2. Fallback to comprehensive personality heuristic
  const heuristic = assignWarmthHeuristic(character, expressions)
  return {
    unlocks: heuristic.unlocks,
    archetypeSummary: heuristic.archetypeSummary,
    method: 'heuristic',
  }
}
