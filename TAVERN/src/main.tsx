import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import '@fontsource-variable/inter/standard.css'
// A second, characterful face for the VN/manga mood — deliberately scoped to character
// name-plates only (VNStage, MessageBubble), not swept across the whole app's editor/settings
import './styles/globals.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
