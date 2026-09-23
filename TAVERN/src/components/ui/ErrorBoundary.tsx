import React, { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Trash2 } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[TAVERN ErrorBoundary caught unhandled error]:', error, errorInfo)
  }

  private handleReload = () => {
    window.location.reload()
  }

  private handleResetAndReload = () => {
    try {
      localStorage.removeItem('rp-settings')
    } catch {
      // ignore
    }
    window.location.reload()
  }

  public override render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen w-full flex-col items-center justify-center bg-[#151515] p-6 text-[#edebe8] font-sans">
          <div className="flex max-w-lg flex-col items-center text-center rounded-xl border border-[#2b2826] bg-[#21201f]/95 p-8 shadow-2xl backdrop-blur-xl">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-[#d97757]/15 text-[#d97757] border border-[#d97757]/30">
              <AlertTriangle size={28} />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-[#edebe8]">
              Something went wrong loading TAVERN
            </h1>
            <p className="mt-2 text-sm text-[#9e9992] leading-relaxed">
              An unexpected render error occurred in the client interface. You can refresh or reset local cached settings.
            </p>

            {this.state.error && (
              <div className="my-5 w-full overflow-hidden rounded-lg border border-[#2b2826] bg-[#191817] p-3 text-left">
                <p className="font-mono text-xs text-[#ef4444] break-words line-clamp-4">
                  {this.state.error.message || String(this.state.error)}
                </p>
              </div>
            )}

            <div className="mt-2 flex w-full flex-col gap-2.5 sm:flex-row">
              <button
                type="button"
                onClick={this.handleReload}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-[#d97757] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#c86646] active:scale-[0.98]"
              >
                <RefreshCw size={15} />
                Reload Studio
              </button>
              <button
                type="button"
                onClick={this.handleResetAndReload}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-[#2b2826] bg-[#2d2b29] px-4 py-2.5 text-sm font-medium text-[#edebe8] transition hover:bg-[#383533] active:scale-[0.98]"
                title="Clears corrupted rp-settings from localStorage and reloads"
              >
                <Trash2 size={15} />
                Reset Settings
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
