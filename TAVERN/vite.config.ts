import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function lucideDirectImports() {
  const map: Record<string, string> = {}
  try {
    const esm = fs.readFileSync(path.resolve(__dirname, 'node_modules/lucide-react/dist/esm/lucide-react.mjs'), 'utf8')
    const regex = /export\s*\{([^}]+)\}\s*from\s*['"]\.\/icons\/([^.'"]+)\.mjs['"]/g
    let m: RegExpExecArray | null
    while ((m = regex.exec(esm)) !== null) {
      const file = m[2]
      const names = m[1].split(',').map(s => s.trim())
      for (const n of names) {
        const asMatch = n.match(/default\s+as\s+(\w+)/)
        if (asMatch) map[asMatch[1]] = file
        else map[n] = file
      }
    }
  } catch (e) {
    console.warn('[lucideDirectImports] could not load icon map', e)
  }

  return {
    name: 'lucide-direct-imports',
    enforce: 'pre' as const,
    transform(code: string, id: string) {
      if (!id.includes('/src/') || (!id.endsWith('.tsx') && !id.endsWith('.ts'))) return null
      if (!code.includes('lucide-react')) return null

      return code.replace(/import\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/g, (_, imports) => {
        const parts = imports.split(',').map((p: string) => p.trim()).filter(Boolean)
        const rewritten: string[] = []
        for (const part of parts) {
          if (part.startsWith('type ')) continue
          const aliasMatch = part.match(/^(\w+)\s+as\s+(\w+)$/)
          if (aliasMatch) {
            const [, original, alias] = aliasMatch
            if (original === 'LucideIcon' || original.startsWith('type ')) continue
            const file = map[original]
            if (file) {
              rewritten.push(`import ${alias} from 'lucide-react/dist/esm/icons/${file}.mjs'`)
            } else {
              rewritten.push(`import { ${original} as ${alias} } from 'lucide-react'`)
            }
          } else {
            if (part === 'LucideIcon' || part.startsWith('type ')) continue
            const file = map[part]
            if (file) {
              rewritten.push(`import ${part} from 'lucide-react/dist/esm/icons/${file}.mjs'`)
            } else {
              rewritten.push(`import { ${part} } from 'lucide-react'`)
            }
          }
        }
        return rewritten.join('\n')
      })
    },
  }
}

export default defineConfig({
  plugins: [lucideDirectImports(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'zustand', 'lucide-react'],
  },
  build: {
    target: 'esnext',
    minify: 'esbuild',
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.PORT) || 5173,
    cors: true,
    allowedHosts: true,
    // Directories that are not app source and that another process writes to while Vite is up —
    // Vite's file watcher crashes the whole dev client with EBUSY the moment one of those files is
    // briefly locked (seen with `presets/`, and again when the sprite generator in `tools/comfy/`
    // wrote a batch of PNGs into `data/avatars/...`). `data/` is on-disk app state served by the
    // API server, never imported; `tools/comfy/out/` and `*.bak-*` are generator scratch/backups.
    // Both a glob and an absolute path are listed for each — the glob alone wasn't reliably
    // matching backslash paths on Windows; chokidar also accepts a plain path prefix.
    watch: {
      ignored: [
        '**/presets/**', path.resolve(__dirname, 'presets'),
        '**/data/**', path.resolve(__dirname, 'data'),
        '**/tools/comfy/out/**', path.resolve(__dirname, 'tools/comfy/out'),
        '**/sprites.bak-*/**',
      ],
    },
    // All app data now lives on disk via the local API server (see server/), reached
    // through this proxy so the browser only ever talks to one origin. If this port
    // were ever busy, Vite's default behavior is to silently bind the next free one
    // instead — same app, but a blank "new" origin with none of your data. Fail loudly
    // instead so a port conflict is obvious, not mistaken for lost data.
    strictPort: true,
    proxy: {
      '/api': `http://localhost:${Number(process.env.API_PORT) || 3001}`,
      '/avatars': `http://localhost:${Number(process.env.API_PORT) || 3001}`,
    },
  },
})
