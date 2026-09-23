import { SingularityImageClient } from './singularityImage'
import { A1111Client } from './a1111Image'
import { ComfyUIClient } from './comfyuiImage'
import { SwarmUIClient } from './swarmuiImage'
import { NovelAIImageClient } from './novelaiImage'
import { OpenMayhemImageClient } from './openMayhemMedia'
import type { ImageBackend, ImageBackendId } from './imageBackend'

export interface ImageBackendSettings {
  openMayhemApiKey?: string
  imageBackend: ImageBackendId
  /** singularity / custom / a1111 / comfyui / swarmui */
  imageBackendBaseUrl: string
  imageBackendUsername: string
  imageBackendPassword: string
  imageBackendModel: string
}

/** Section 11's image-backend factory — the `createChatBackend` pattern applied to image generation. */
export function createImageBackend(settings: ImageBackendSettings): ImageBackend {
  switch (settings.imageBackend) {
    case 'singularity':
    case 'universal-gift':
    case 'chatgpt-image':
      return new SingularityImageClient(settings.imageBackendBaseUrl || 'http://localhost:9000/v1')
    case 'custom':
      return new SingularityImageClient(settings.imageBackendBaseUrl || 'http://localhost:9000/v1')
    case 'openmayhem':
      return new OpenMayhemImageClient(settings.openMayhemApiKey || '', settings.imageBackendModel)
    case 'novelai-image':
      return new NovelAIImageClient(settings.imageBackendUsername, settings.imageBackendModel)
    case 'comfyui':
      return new ComfyUIClient(settings.imageBackendBaseUrl)
    case 'swarmui':
      return new SwarmUIClient(settings.imageBackendBaseUrl)
    case 'a1111':
      return new A1111Client(settings.imageBackendBaseUrl, settings.imageBackendUsername || undefined, settings.imageBackendPassword || undefined)
    default:
      return new SingularityImageClient(settings.imageBackendBaseUrl || 'http://localhost:9000/v1')
  }
}
