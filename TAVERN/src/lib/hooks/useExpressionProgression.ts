import { useEffect, useMemo, useRef, useState } from 'react'
import { extractExpressionTimeline, type ExpressionBeat } from '@/lib/vn/expressionInference'

export interface UseExpressionProgressionOptions {
  /** Identifier of the message to reset state cleanly across turns or swipes */
  messageId?: string | null
  /** Complete text of the active character message */
  text: string
  /** Initial expression tag if declared on the message / sticky scene */
  initialExpression?: string
  /** Unlocked or candidate expression IDs for the character */
  allowedExpressionIds?: string[]
  /** Number of characters revealed so far (e.g. from useTypewriterReveal) */
  revealedTextLength?: number
  /** Whether typewriter effect is actively revealing character-by-character */
  typewriterActive?: boolean
  /** Whether the message is still being streamed token-by-token */
  isStreaming?: boolean
  /** Reduced motion setting */
  reducedMotion?: boolean
  /** Reading speed in words per minute for timer calculation (default ~300 WPM, fast reader pace) */
  wpm?: number
}

export interface UseExpressionProgressionResult {
  /** Current active expression to display on sprite/portrait */
  currentExpression: string
  /** Full ordered emotional timeline extracted for this message */
  timeline: ExpressionBeat[]
  /** Index of currently active beat in timeline */
  activeBeatIndex: number
}

const DEFAULT_WPM = 300
const MIN_BEAT_DELAY_MS = 2500
const MAX_BEAT_DELAY_MS = 18000

/**
 * Hook that manages dynamic multi-expression progression across a single character response.
 *
 * Rather than remaining frozen on an initial smirk throughout a long reply, the character's
 * active sprite transitions sequentially as the reader reads:
 * - When typewriter is actively revealing text, transitions occur when the reveal reaches
 *   the offset of the emotional shift.
 * - When typewriter is inactive or skipped, a reading-speed timer based on word distance
 *   transitions between sprites at a natural reading pace (~300 WPM).
 */
export function useExpressionProgression({
  messageId,
  text,
  initialExpression,
  allowedExpressionIds = [],
  revealedTextLength,
  typewriterActive = false,
  isStreaming = false,
  wpm = DEFAULT_WPM,
}: UseExpressionProgressionOptions): UseExpressionProgressionResult {
  const allowedKey = allowedExpressionIds.join(',')

  const timeline = useMemo(() => {
    return extractExpressionTimeline(text, allowedExpressionIds, initialExpression)
  }, [text, initialExpression, allowedKey])

  const [activeBeatIndex, setActiveBeatIndex] = useState(0)
  const prevMsgIdRef = useRef<string | null | undefined>(messageId)

  // Reset progression when message changes
  useEffect(() => {
    if (prevMsgIdRef.current !== messageId) {
      prevMsgIdRef.current = messageId
      setActiveBeatIndex(0)
    }
  }, [messageId])

  // Reset if timeline changes significantly
  useEffect(() => {
    setActiveBeatIndex((prev) => (prev >= timeline.length ? Math.max(0, timeline.length - 1) : prev))
  }, [timeline.length])

  // 1. Typewriter synchronization: advance when typewriter reaches the beat's text offset
  useEffect(() => {
    if (!typewriterActive || isStreaming || revealedTextLength === undefined || revealedTextLength <= 0) {
      return
    }

    if (activeBeatIndex + 1 < timeline.length) {
      const nextBeat = timeline[activeBeatIndex + 1]
      if (revealedTextLength >= nextBeat.charIndex) {
        setActiveBeatIndex((prev) => Math.max(prev, activeBeatIndex + 1))
      }
    }
  }, [revealedTextLength, typewriterActive, isStreaming, activeBeatIndex, timeline])

  // 2. Reading timer progression: advance based on reader pace when typewriter is not driving
  useEffect(() => {
    if (typewriterActive || isStreaming || timeline.length <= 1) {
      return
    }

    if (activeBeatIndex + 1 >= timeline.length) {
      return
    }

    const currentBeat = timeline[activeBeatIndex]
    const nextBeat = timeline[activeBeatIndex + 1]
    const deltaWords = Math.max(1, nextBeat.wordIndex - currentBeat.wordIndex)
    const msPerWord = (60 / Math.max(100, wpm)) * 1000
    const rawDelayMs = deltaWords * msPerWord
    const delayMs = Math.max(MIN_BEAT_DELAY_MS, Math.min(MAX_BEAT_DELAY_MS, Math.round(rawDelayMs)))

    const timer = setTimeout(() => {
      setActiveBeatIndex((prev) => {
        if (prev === activeBeatIndex && prev + 1 < timeline.length) {
          return prev + 1
        }
        return prev
      })
    }, delayMs)

    return () => clearTimeout(timer)
  }, [activeBeatIndex, timeline, typewriterActive, isStreaming, wpm])

  const currentExpression =
    timeline[activeBeatIndex]?.expression || initialExpression || 'neutral'

  return {
    currentExpression,
    timeline,
    activeBeatIndex,
  }
}
