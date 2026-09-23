import { describe, expect, it } from 'vitest'
import {
  currentExpressionFrom,
  currentTaggedBackgroundFrom,
  currentSceneImageFrom,
  type SceneCarrier,
} from './stickyScene'

describe('stickyScene', () => {
  describe('currentExpressionFrom', () => {
    it('returns neutral for empty messages', () => {
      expect(currentExpressionFrom([])).toBe('neutral')
    })

    it('returns neutral if no character message has an expression', () => {
      const msgs: SceneCarrier[] = [
        { role: 'user', text: 'Hello!' },
        { role: 'char', text: 'Hi.' },
      ]
      expect(currentExpressionFrom(msgs)).toBe('neutral')
    })

    it('retains expression from turn 1 when turn 2 placeholder is generating with no expression', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'Nice to meet you!', scene: { expression: 'smirk' } },
        { role: 'user', text: 'You too.' },
        { role: 'char', text: '' }, // Turn 2 generating placeholder
      ]
      expect(currentExpressionFrom(msgs)).toBe('smirk')
    })

    it('switches to new expression once turn 2 provides one', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'Nice to meet you!', scene: { expression: 'smirk' } },
        { role: 'user', text: 'You too.' },
        { role: 'char', text: 'Haha!', scene: { expression: 'laughing' } },
      ]
      expect(currentExpressionFrom(msgs)).toBe('laughing')
    })

    it('filters by speakerId when provided', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', speakerId: 'aria', text: 'Hey', scene: { expression: 'happy' } },
        { role: 'char', speakerId: 'sumire', text: 'Hello', scene: { expression: 'annoyed' } },
        { role: 'user', text: '...' },
        { role: 'char', speakerId: 'aria', text: '' }, // Aria generating
      ]
      expect(currentExpressionFrom(msgs, 'aria')).toBe('happy')
      expect(currentExpressionFrom(msgs, 'sumire')).toBe('annoyed')
    })

    it('reads from swipeScenes when activeSwipe is set', () => {
      const msgs: SceneCarrier[] = [
        {
          role: 'char',
          text: 'Swipe message',
          swipeScenes: [{ expression: 'sad' }, { expression: 'flirty' }],
          activeSwipe: 1,
        },
        { role: 'char', text: '' },
      ]
      expect(currentExpressionFrom(msgs)).toBe('flirty')
    })
  })

  describe('currentTaggedBackgroundFrom', () => {
    it('returns undefined for empty messages', () => {
      expect(currentTaggedBackgroundFrom([])).toBeUndefined()
    })

    it('retains background from turn 1 when turn 2 is generating', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'In the gym', scene: { background: 'Gymnasium' } },
        { role: 'user', text: 'Looking around' },
        { role: 'char', text: '' }, // Turn 2 generating
      ]
      expect(currentTaggedBackgroundFrom(msgs)).toBe('Gymnasium')
    })

    it('retains background across turns if turn 2 does not specify a new background', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'Welcome to the gym', scene: { background: 'Gymnasium', expression: 'smirk' } },
        { role: 'user', text: 'Thanks' },
        { role: 'char', text: 'Ready to practice?', scene: { expression: 'happy' } }, // No background specified
      ]
      expect(currentTaggedBackgroundFrom(msgs)).toBe('Gymnasium')
    })

    it('switches to new background when explicitly declared', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'In gym', scene: { background: 'Gymnasium' } },
        { role: 'user', text: 'Let us go to the roof' },
        { role: 'char', text: 'On the roof now', scene: { background: 'Rooftop' } },
      ]
      expect(currentTaggedBackgroundFrom(msgs)).toBe('Rooftop')
    })
  })

  describe('currentSceneImageFrom', () => {
    it('returns undefined if no messages have images', () => {
      expect(currentSceneImageFrom([])).toBeUndefined()
    })

    it('retains backdrop image from previous message when location is the same', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'Gym shot', images: ['https://example.com/gym.png'], scene: { background: 'Gymnasium' } },
        { role: 'user', text: 'Cool place' },
        { role: 'char', text: '' }, // Generating
      ]
      expect(currentSceneImageFrom(msgs, 'Gymnasium')).toBe('https://example.com/gym.png')
    })

    it('discards previous image if scene moved to a new location', () => {
      const msgs: SceneCarrier[] = [
        { role: 'char', text: 'Gym shot', images: ['https://example.com/gym.png'], scene: { background: 'Gymnasium' } },
        { role: 'user', text: 'Let us go' },
        { role: 'char', text: 'Now on roof', scene: { background: 'Rooftop' } },
      ]
      expect(currentSceneImageFrom(msgs, 'Rooftop')).toBeUndefined()
    })
  })
})
