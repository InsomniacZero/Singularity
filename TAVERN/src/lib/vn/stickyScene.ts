/**
 * Visual Novel scene continuity helpers.
 *
 * In visual novels, scenes and character expressions are continuous across turns:
 * 1. An expression must not reset to neutral while the next line is generating or if a reply
 *    leaves expression unspecified — the character holds their emotion until a new expression is established.
 * 2. A background must not disappear into void/black while a reply is generating or across turns in the same room.
 *    The stage retains the current location and illustrated backdrop until a new location is explicitly introduced.
 */

export interface SceneCarrier {
  role: string
  speakerId?: string | null
  text?: string
  images?: string[]
  scene?: {
    expression?: string
    background?: string
    outfit?: string
    mood?: string
  }
  swipeScenes?: ({
    expression?: string
    background?: string
    outfit?: string
    mood?: string
  } | undefined)[]
  activeSwipe?: number
}

/**
 * Resolves the active expression for a character, retaining the last explicit
 * expression from earlier in the scene if the current message is generating or
 * leaves the expression unspecified.
 */
export function currentExpressionFrom(
  messages: readonly SceneCarrier[],
  speakerId?: string | null,
): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.role !== 'char') continue
    if (speakerId && m.speakerId && m.speakerId !== speakerId) continue

    const scene = m.swipeScenes?.[m.activeSwipe ?? 0] ?? m.scene
    const exp = scene?.expression?.trim()
    if (exp) return exp
  }

  return 'neutral'
}

/**
 * Resolves the active tagged background, retaining the last explicit location
 * from earlier in the scene if the current message is generating or doesn't declare a move.
 */
export function currentTaggedBackgroundFrom(
  messages: readonly SceneCarrier[],
): string | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    const scene = m.swipeScenes?.[m.activeSwipe ?? 0] ?? m.scene
    const bg = scene?.background?.trim()
    if (bg) return bg
  }
  return undefined
}

/**
 * Resolves the active background image attached to messages, retaining the most recent
 * illustrated backdrop as long as the scene hasn't moved to a different tagged location.
 */
export function currentSceneImageFrom(
  messages: readonly SceneCarrier[],
  currentLocation?: string | null,
): string | undefined {
  const normCurrent = currentLocation?.trim().toLowerCase()
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.images && m.images.length > 0 && m.images[0]) {
      const scene = m.swipeScenes?.[m.activeSwipe ?? 0] ?? m.scene
      const msgBg = scene?.background?.trim().toLowerCase()
      // If the message had a specific background, ensure we are still at that location or no location is set
      if (!normCurrent || !msgBg || msgBg === normCurrent) {
        return m.images[0]
      }
      // If the message had a different location tagged than current location, stop looking further back
      break
    }
  }
  return undefined
}
