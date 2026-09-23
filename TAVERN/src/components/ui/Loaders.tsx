import React from 'react'

/**
 * Thematic Motion Graphic Loaders per DESIGN-SYS.md Section 8.
 * Generic spinning wheels are banned; these loaders provide clear modal feedback.
 */

/**
 * Dual-concentric orbital rings pulsing with glowing nodes and elapsed timer.
 * Used for reasoning models (DeepSeek Reasoner, Kimi Thinking, Qwen Thinking).
 */
export function ReasoningPulseLoader({ label = 'Reasoning process active…', elapsedSeconds }: { label?: string; elapsedSeconds?: number }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-accent/25 bg-accent/5 px-3 py-2 text-xs text-text backdrop-blur-sm">
      <div className="relative flex h-5 w-5 items-center justify-center">
        {/* Outer orbital ring */}
        <span className="absolute h-5 w-5 animate-spin rounded-full border border-dashed border-accent/40 [animation-duration:4s]" />
        {/* Inner pulsing ring */}
        <span className="absolute h-3 w-3 animate-ping rounded-full bg-accent/20 [animation-duration:2s]" />
        {/* Central glowing core node */}
        <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_8px_rgba(217,119,87,0.8)]" />
      </div>
      <span className="font-mono text-xs text-text-muted">{label}</span>
      {elapsedSeconds !== undefined && (
        <span className="ml-auto font-mono text-[11px] text-accent/80 tabular-nums">
          {elapsedSeconds.toFixed(1)}s
        </span>
      )}
    </div>
  )
}

/**
 * Glowing dot matrix shimmer across an aspect-ratio frame.
 * Used for image generation (Singularity scene illustration, Nano Banana, ComfyUI).
 */
export function ImageMatrixLoader({ label = 'Synthesizing scene artwork…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-border/80 bg-bg-sunken/60 p-6 text-center">
      {/* 3x3 Dot Matrix Shimmer */}
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 9 }).map((_, i) => (
          <span
            key={i}
            className="h-2 w-2 rounded-sm bg-accent/30 animate-pulse"
            style={{ animationDelay: `${(i % 5) * 180}ms`, animationDuration: '1.4s' }}
          />
        ))}
      </div>
      <span className="font-mono text-xs text-text-muted tracking-wide">{label}</span>
    </div>
  )
}
