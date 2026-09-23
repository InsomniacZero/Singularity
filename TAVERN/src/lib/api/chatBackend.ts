import type { GenerateRequest } from './types'

// Shared interface implemented by `KoboldClient` and every hosted-provider client, plus the
// provider metadata (ids, labels, known OpenAI-compatible providers) used to pick between them.

export interface ChatBackend {
  /** Opt JSON-producing assists into an object envelope and a validated JSON-mode request. */
  readonly prefersJsonObject?: boolean
  generate(params: GenerateRequest, signal?: AbortSignal): Promise<string>
  generateStream(params: GenerateRequest, onToken: (token: string, full: string) => void, signal?: AbortSignal): Promise<string>
  /** The model's actual max context, cached — or a sane fallback for a backend with no introspection endpoint. */
  getEffectiveMaxContext(fallback?: number): Promise<number>
  tokenCount(text: string): Promise<{ count: number }>
  /** Best-effort server-side abort — a no-op for a backend with no such endpoint. */
  abort(genkey: string): Promise<void>
  /** The loaded model's own chat template — always null for a backend that isn't running a local GGUF. */
  getChatTemplate(): Promise<string | null>
}

/** Lightweight reachability+auth probe implemented by every non-KoboldCpp backend, for Settings → Connection. */
export interface ConnectionCheckResult {
  ok: boolean
  /** A short, specific reason for a failure — undefined for success or an unexplained failure. */
  detail?: string
}

export type ChatBackendId = 'koboldcpp' | 'openai-compatible' | 'novelai'

export const CHAT_BACKEND_LABELS: Record<ChatBackendId, string> = {
  'openai-compatible': 'Singularity / Custom API (OpenAI-compatible)',
  koboldcpp: 'KoboldCpp (local)',
  novelai: 'NovelAI (hosted, subscription)',
}

/** NovelAI's own two current text models this app supports. */
export const NOVELAI_MODELS = [
  { id: 'kayra-v1', label: 'Kayra' },
  { id: 'clio-v1', label: 'Clio' },
] as const

export interface ChatBackendConfig {
  backend: ChatBackendId
  /** 'openai-compatible' only. */
  baseUrl: string
  apiKey: string
  model: string
}

export interface KnownChatProvider {
  id: string
  label: string
  baseUrl: string
  /** Shown as the Model field's placeholder once this provider is picked. */
  modelExample: string
}

/** Provider picker: Singularity Unified Gateway is default; one slot open for Custom API. */
export const KNOWN_CHAT_PROVIDERS: KnownChatProvider[] = [
  {
    id: 'singularity',
    label: 'Singularity Gateway (Unified Local AI Fleet)',
    baseUrl: 'http://localhost:9000/v1',
    modelExample: 'gemini-3.8-flash',
  },
  {
    id: 'custom',
    label: 'Custom API (OpenAI-compatible)',
    baseUrl: 'http://localhost:1234/v1',
    modelExample: 'custom-model',
  },
]
