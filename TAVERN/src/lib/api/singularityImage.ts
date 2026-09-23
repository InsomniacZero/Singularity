import { KoboldApiError } from './types'
import type { ImageBackend, ImageGenerateParams, ImageGenerateResult } from './imageBackend'

export class SingularityImageClient implements ImageBackend {
  constructor(private baseUrl: string = 'http://localhost:9000/v1') {}

  private url(path: string): string {
    const root = this.baseUrl.replace(/\/+$/, '')
    return (root.endsWith('/v1') ? root : `${root}/v1`) + path
  }

  async generateImage(params: ImageGenerateParams, signal?: AbortSignal): Promise<ImageGenerateResult> {
    let referenceImage = params.referenceImage
    if (referenceImage && !referenceImage.startsWith('data:') && !referenceImage.startsWith('http')) {
      try {
        const fetchRes = await fetch(referenceImage)
        if (fetchRes.ok) {
          const blob = await fetchRes.blob()
          referenceImage = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(String(reader.result))
            reader.onerror = reject
            reader.readAsDataURL(blob)
          })
        }
      } catch (err) {
        console.warn('SingularityImageClient: Could not convert referenceImage to data URL:', err)
      }
    }

    let prompt = params.prompt.trim()
    if (params.transparent && !prompt.toLowerCase().includes('transparent') && !prompt.toLowerCase().includes('green background')) {
      prompt = `${prompt}, isolated character sprite on transparent background, PNG with alpha channel, no backdrop, centered composition`
    }

    let res: Response
    try {
      res = await fetch(this.url('/images/generations'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal,
        body: JSON.stringify({
          prompt,
          model: params.model || 'gemini-3.8-flash',
          response_format: 'b64_json',
          reference_image: referenceImage,
          transparent: params.transparent ?? true,
          n: 1,
          size: `${params.width || 1024}x${params.height || 1536}`,
        }),
      })
    } catch (e) {
      if (signal?.aborted) throw e
      throw new KoboldApiError(`Could not reach Singularity Gateway at ${this.baseUrl}. Is the server running?`)
    }

    if (!res.ok) {
      let msg = ''
      try {
        const errJson = await res.json()
        msg = errJson?.error?.message || errJson?.error || errJson?.detail || ''
      } catch {
        msg = await res.text().catch(() => '')
      }
      throw new KoboldApiError(
        `Singularity image generation failed (${res.status}): ${typeof msg === 'string' ? msg.slice(0, 300) : JSON.stringify(msg)}`,
        res.status
      )
    }

    const data = (await res.json()) as { data?: { b64_json?: string; url?: string }[] }
    const first = data.data?.[0]
    if (!first?.b64_json && !first?.url) {
      throw new KoboldApiError('Singularity Gateway returned no image data.')
    }

    // If only URL returned, fetch bytes and convert to base64 so TAVERN local storage/canvas gets base64
    let base64 = first.b64_json ?? ''
    if (!base64 && first.url) {
      try {
        const imgRes = await fetch(first.url)
        const buf = await imgRes.arrayBuffer()
        base64 = btoa(String.fromCharCode(...new Uint8Array(buf)))
      } catch {
        // keep fallback
      }
    }

    return {
      base64,
      mimeType: 'image/png',
    }
  }

  async listModels(): Promise<string[]> {
    try {
      const res = await fetch(this.url('/models'))
      if (res.ok) {
        const data = (await res.json()) as { data?: { id: string; capabilities?: string[] }[] }
        if (Array.isArray(data.data) && data.data.length > 0) {
          const imageModels = data.data
            .filter((m) => m.capabilities?.includes('image') || m.id.includes('image') || m.id.includes('imagine') || m.id.includes('flash'))
            .map((m) => m.id)
          if (imageModels.length > 0) return imageModels
        }
      }
    } catch {
      // fallback on failure
    }
    return ['gemini-3.8-flash', 'gpt-image-2.5-flare', 'grok-imagine-1.5', 'glm-image-1', 'nano-banana-pro']
  }
}
