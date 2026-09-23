/**
 * Section 11's "image/asset generation backends" — the same "one interface, many providers" shape
 * as `ChatBackend`/`ttsProviders.ts`, this time for generating an image into a slot (character
 * avatar, VN sprite, world background, gallery CG) that today only accepts an upload. Deliberately
 * minimal: one call to generate, one to list what models/checkpoints are available (best-effort —
 * a backend with no such introspection, or one that's unreachable, returns an empty list rather
 * than throwing, since the picker just falls back to a free-text field in that case).
 */
export interface ImageGenerateParams {
  prompt: string
  negativePrompt?: string
  width: number
  height: number
  steps: number
  cfgScale: number
  /** Omit (or -1) for a random seed — every backend here treats that the same way. */
  seed?: number
  /** Checkpoint/model name — meaning is backend-specific; omit to use whatever's already loaded. */
  model?: string
  sampler?: string
  /** Reference image (data URL or base64) for character consistency across expressions */
  referenceImage?: string
  /** Cut out background to produce transparent character sprite */
  transparent?: boolean
}

export interface ImageGenerateResult {
  /** Base64-encoded image bytes, no `data:` prefix — callers wrap it into a data URL themselves (matches how `decodeImageDataUrl` on the server already expects one). */
  base64: string
  mimeType?: string
  /** The seed actually used, when the backend reports it — useful since `params.seed` is often left unset for a random one. */
  seed?: number
}

export interface ImageBackend {
  generateImage(params: ImageGenerateParams, signal?: AbortSignal): Promise<ImageGenerateResult>
  listModels(): Promise<string[]>
}

export type ImageBackendId =
  | 'singularity'
  | 'custom'
  | 'a1111'
  | 'comfyui'
  | 'swarmui'
  | 'universal-gift'
  | 'chatgpt-image'
  | 'novelai-image'
  | 'openmayhem'

export const SINGULARITY_IMAGE_MODELS = [
  'gemini-3.8-flash',
  'gpt-image-2.5-flare',
  'grok-imagine-1.5',
  'glm-image-1',
  'nano-banana-pro',
] as const

export const CHATGPT_IMAGE_MODELS = [
  'gpt-image-2.5-flare',
  'gpt-image-2.5-sunburst',
  'gpt-image-2',
] as const

export const IMAGE_BACKEND_LABELS: Record<ImageBackendId, string> = {
  singularity: 'Singularity Gateway (Local Unified AI Fleet)',
  custom: 'Custom Image API (OpenAI-compatible /v1/images/generations)',
  a1111: 'Automatic1111 / Forge (local)',
  comfyui: 'ComfyUI (local)',
  swarmui: 'SwarmUI (local)',
  'universal-gift': 'Singularity Gateway (Legacy Alias)',
  'chatgpt-image': 'Singularity / ChatGPT Image (Legacy Alias)',
  'novelai-image': 'NovelAI (hosted, subscription)',
  openmayhem: 'OpenMayhem (hosted)',
}

