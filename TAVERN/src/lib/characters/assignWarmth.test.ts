import { describe, expect, it } from 'vitest'
import {
  assignWarmthHeuristic,
  detectPersonalityTraits,
  assignExpressionWarmth,
} from './assignWarmth'
import { DEFAULT_EXPRESSIONS } from '@/lib/vn/expressions'

describe('assignWarmth', () => {
  const expressions = DEFAULT_EXPRESSIONS.map((e) => ({ id: e.id, label: e.label }))

  it('detects Tsundere traits accurately and keeps conversational expressions at 0 while gating blush/love', () => {
    const character = {
      name: 'Asuka',
      personality: 'Tsundere, prickly, defensive, calls you idiot (baka!), stubborn, secretly soft interior',
    }

    const traits = detectPersonalityTraits(character.personality)
    expect(traits.isTsundere).toBe(true)

    const result = assignWarmthHeuristic(character, expressions)
    // Conversational / situational expressions are 0 from turn 1
    expect(result.unlocks.neutral).toBe(0)
    expect(result.unlocks.happy).toBe(0)
    expect(result.unlocks.laughing).toBe(0)
    expect(result.unlocks.smirk).toBe(0)
    expect(result.unlocks.annoyed).toBe(0)
    expect(result.unlocks.angry).toBe(0)
    expect(result.unlocks.surprised).toBe(0)

    // Romantic & intimate expressions require warmth progression
    expect(result.unlocks.blush).toBe(20)
    expect(result.unlocks.love).toBe(40)
    expect(result.unlocks.crying).toBe(30)
    expect(result.unlocks.aroused).toBe(55)
  })

  it('detects Seductive / Flirty traits and assigns low warmth to smirk, flirty, and sultry', () => {
    const character = {
      name: 'Carmilla',
      personality: 'Seductive succubus, flirty, teasing, sensual, coquettish, playful',
    }

    const traits = detectPersonalityTraits(character.personality)
    expect(traits.isSeductive).toBe(true)

    const result = assignWarmthHeuristic(character, expressions)
    expect(result.unlocks.smirk).toBe(0)
    expect(result.unlocks.flirty).toBe(0)
    expect(result.unlocks.laughing).toBe(0)
    expect(result.unlocks.sultry).toBe(10)

    // True emotional vulnerability (blush, love) requires genuine warmth
    expect(result.unlocks.blush).toBe(25)
    expect(result.unlocks.love).toBe(30)
  })

  it('detects Genki / Cheerful traits and keeps conversational emotions at 0', () => {
    const character = {
      name: 'Yui',
      personality: 'Genki, bubbly, energetic, cheerful, extrovert, always smiling and optimistic',
    }

    const traits = detectPersonalityTraits(character.personality)
    expect(traits.isGenki).toBe(true)

    const result = assignWarmthHeuristic(character, expressions)
    expect(result.unlocks.happy).toBe(0)
    expect(result.unlocks.laughing).toBe(0)
    expect(result.unlocks.surprised).toBe(0)
    expect(result.unlocks.neutral).toBe(0)
  })

  it('falls back seamlessly to heuristic when no backend client is passed', async () => {
    const character = {
      name: 'Rei',
      personality: 'Kuudere, stoic, aloof, emotionless, quiet, deadpan',
      description: 'A quiet pilot who rarely expresses emotion.',
      scenario: 'Meeting at the hangar.',
      first_mes: '',
      mes_example: '',
      creator_notes: '',
      system_prompt: '',
      post_history_instructions: '',
      alternate_greetings: [],
      tags: [],
      creator: '',
      character_version: '',
      extensions: {},
    }

    const res = await assignExpressionWarmth(character, expressions, null)
    expect(res.method).toBe('heuristic')
    expect(res.unlocks.neutral).toBe(0)
    expect(res.unlocks.laughing).toBe(0)
    expect(res.unlocks.blush).toBe(25)
    expect(res.unlocks.love).toBe(40)
    expect(res.archetypeSummary).toContain('Kuudere')
  })
})
