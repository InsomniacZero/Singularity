import { describe, expect, it } from 'vitest'
import { extractExpressionTimeline, inferExpressionFromText } from './expressionInference'

describe('inferExpressionFromText', () => {
  const allowed = [
    'neutral',
    'happy',
    'smirk',
    'laughing',
    'sad',
    'crying',
    'angry',
    'annoyed',
    'surprised',
    'scared',
    'blush',
    'pain',
    'thinking',
  ]

  it('infers laughing or smirk from a sharp laugh and crooked grin', () => {
    const text =
      'Aria winces, jumping backward with a sharp laugh as her hand instinctively comes up to block Kai\'s arm. "Whoa—hey to yourself, Kai, we are practically strangers." She settles back, a crooked, playful grin staying on her face as she watches him carefully.'
    const inferred = inferExpressionFromText(text, allowed)
    expect(['laughing', 'smirk']).toContain(inferred)
  })

  it('infers angry from glare and scowl', () => {
    const text = 'She crossed her arms with a fierce glare, scowling darkly at him. "Do not test my patience."'
    const inferred = inferExpressionFromText(text, allowed)
    expect(inferred).toBe('angry')
  })

  it('infers blush from crimson cheeks', () => {
    const text = 'Her cheeks burned crimson as she looked away, flustered and stammering.'
    const inferred = inferExpressionFromText(text, allowed)
    expect(inferred).toBe('blush')
  })

  it('returns null if no strong emotional cues match or if matched emotion is locked', () => {
    const text = 'The car drove down the quiet street under the lamppost.'
    expect(inferExpressionFromText(text, allowed)).toBeNull()

    // If laughing is not in allowed, it shouldn't pick it
    const restricted = ['neutral', 'sad']
    const laughText = 'She cracked up with a loud laugh.'
    expect(inferExpressionFromText(laughText, restricted)).toBeNull()
  })
})

describe('extractExpressionTimeline', () => {
  const allowed = ['neutral', 'happy', 'smirk', 'thinking', 'sad', 'blush', 'laughing']

  it("extracts emotional progression for Yelena's library scenario (smirk -> thinking)", () => {
    const yelenaResponse =
      'Yelena closes the book in front of her and looks up from the library table as You approaches. She brushes a strand of hair behind her ear and gives a small, amused smile. "I was wondering when you would show up."\n\n' +
      'She glances toward the empty chairs around her, then taps the seat across from her with her pen. "Sit down. I need an excuse to stay here a little longer, and you are better company than a textbook."\n\n' +
      'She looks out the window at the cherry trees below the hill before meeting You\'s eyes again. "Can I ask you something? Do you ever get tired of everyone seeing only the version of you they already decided on?"'

    const timeline = extractExpressionTimeline(yelenaResponse, allowed, 'smirk')
    expect(timeline.length).toBe(2)
    expect(timeline[0].expression).toBe('smirk')
    expect(timeline[0].wordIndex).toBe(0)
    expect(timeline[1].expression).toBe('thinking')
    expect(timeline[1].wordIndex).toBeGreaterThan(50)
  })

  it('infers initial emotion from opening prose when no initial tag is provided', () => {
    const yelenaResponse =
      'Yelena closes the book in front of her and looks up from the library table as You approaches. She brushes a strand of hair behind her ear and gives a small, amused smile. "I was wondering when you would show up."\n\n' +
      'She looks out the window at the cherry trees below the hill before meeting You\'s eyes again. "Can I ask you something?"'

    const timeline = extractExpressionTimeline(yelenaResponse, allowed)
    expect(timeline.length).toBe(2)
    expect(timeline[0].expression).toBe('smirk')
    expect(timeline[1].expression).toBe('thinking')
  })

  it('handles explicit mid-text tags with exact positions', () => {
    const tagged =
      '<<scene:expression=smirk>> She smiles with a sly grin. "Got you."\n\n' +
      '<<scene:expression=blush>> But then her cheeks turn red. "Wait, really?"'

    const timeline = extractExpressionTimeline(tagged, allowed)
    expect(timeline.length).toBe(2)
    expect(timeline[0].expression).toBe('smirk')
    expect(timeline[1].expression).toBe('blush')
  })

  it('keeps single beat when character maintains one emotion', () => {
    const cheerful = 'She smiled warmly and waved. "Good morning! It is wonderful to see you today."'
    const timeline = extractExpressionTimeline(cheerful, allowed, 'happy')
    expect(timeline.length).toBe(1)
    expect(timeline[0].expression).toBe('happy')
  })
})

