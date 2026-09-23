import type { Config } from 'tailwindcss'

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Plus Jakarta Sans',
          'Inter Variable',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'monospace',
        ],
        display: [
          'Plus Jakarta Sans',
          'sans-serif',
        ],
      },
      colors: {
        bg: 'rgb(var(--c-bg) / <alpha-value>)',
        'bg-elevated': 'rgb(var(--c-bg-elevated) / <alpha-value>)',
        'bg-sunken': 'rgb(var(--c-bg-sunken) / <alpha-value>)',
        border: 'rgb(var(--c-border) / <alpha-value>)',
        'border-subtle': 'rgb(var(--c-border) / <alpha-value>)',
        'border-medium': 'rgb(var(--c-border-medium, var(--c-border)) / <alpha-value>)',
        text: 'rgb(var(--c-text) / <alpha-value>)',
        'text-muted': 'rgb(var(--c-text-muted) / <alpha-value>)',
        accent: 'rgb(var(--c-accent) / <alpha-value>)',
        'accent-hover': '#c86646',
        'accent-text': 'rgb(var(--c-accent-text) / <alpha-value>)',
        brand: 'rgb(var(--c-accent) / <alpha-value>)',
        'msg-user': 'rgb(var(--c-msg-user) / <alpha-value>)',
        'msg-char': 'rgb(var(--c-msg-char) / <alpha-value>)',
        danger: 'rgb(var(--c-danger) / <alpha-value>)',
        success: 'rgb(var(--c-success) / <alpha-value>)',
        warning: 'rgb(var(--c-warning) / <alpha-value>)',
        romance: 'rgb(var(--c-romance) / <alpha-value>)',
        'romance-text': 'rgb(var(--c-romance-text) / <alpha-value>)',
      },
      borderRadius: {
        DEFAULT: 'var(--radius, 8px)',
        xs: '4px',
        sm: '6px',
        md: '8px',
        lg: '10px',
        xl: '12px',
        '2xl': '14px',
      },
      fontSize: {
        base: 'calc(1rem * var(--font-scale, 1))',
      },
      maxWidth: {
        chat: 'var(--chat-width, 56rem)',
      },
      backdropBlur: {
        chat: 'var(--chat-blur, 0px)',
      },
      transitionDuration: {
        DEFAULT: 'var(--motion-duration, 150ms)',
      },
    },
  },
  plugins: [],
} satisfies Config
