# 🏛️ Universal Design System Specification (`DESIGN-SYS.md`)
> **The Universal Visual, Architectural & Interaction Design Standard for All Applications & Tools.**
> *Flagship Reference Implementation: Singularity AI Gateway & Control Center*
> *Last Updated: September 2026*

---

> [!IMPORTANT]
> **Universal Scope Across All Projects**:
> This document is the single source of truth for **all current and future web applications, admin tools, dashboards, and developer interfaces** built in this environment. Whether building a full-stack dashboard, a desktop utility, or a micro-tool, adhere strictly to these rules, tokens, and component guidelines.

---

## 🎯 1. Core Philosophy: The Warm Stone & Technical Editorial Aesthetic

Every application built under this design system is engineered with a strict **editorial, high-density, instrument-grade aesthetic** known internally as **Warm Stone & Terracotta** (or Deep Obsidian).

### Principles
1. **Precision Instrument, Not Marketing Toy**: The interface prioritizes density, telemetry, clear hierarchy, and immediate control over frivolous consumer-facing gimmicks.
2. **Editorial Restraint**: Color is applied intentionally. Surfaces are deep neutral stone (`#151515` to `#21201f`) with a single signature accent—**Terracotta Red/Orange (`#d97757`)**—and project/service-specific accents reserved strictly for badges, status indicators, and syntax highlights.
3. **Tactile Geometry**: Everything has deliberate structure. Radii are crisp (4px, 6px, 8px, 10px). Micro-interactions provide tactile feedback (`scale(0.98)` on click) without laggy spring physics.
4. **100dvh Lock & Viewport Mastery**: Applications never let the window body scroll freely. Every panel is contained within the viewport (`100dvh`), with internal panels handling their own independent, smooth scrolling.

---

## 🚫 2. The Strict "DO NOT" List (Forbidden Patterns)

Any contributor, agent, or developer creating or modifying user interfaces across any of our projects **MUST NEVER** introduce the following anti-patterns:

| ❌ Strictly Forbidden Pattern | Why It Is Banned | ✅ Required Standard |
| :--- | :--- | :--- |
| **Pill-Shaped Buttons (`rounded-full` / `9999px`)** | Looks like a cheap consumer app or toy. Destroys visual rhythm in technical dashboards. | Use structured geometric radii: `var(--radius-sm)` (6px) or `var(--radius-md)` (8px). |
| **Over-the-Top Saturated Gradients** | Multi-color rainbow or vibrant purple/cyan gradients feel dated, noisy, and unpolished. | Flat, refined surfaces with **1px solid subtle warm borders** (`#2b2826`). Only very soft (2–3% opacity) radial glows are permitted. |
| **Cramped / Centered 600px Max-Width Wrappers** | Wastes screen real estate on desktop monitors where users want to see fleet telemetry, multiple accounts, and wide code blocks. | **Maximize full screen width (`100vw`)** with high-density CSS grids (`repeat(auto-fill, minmax(360px, 1fr))`) and flex columns. |
| **Unnecessary AI Boilerplate & Marketing Subtitles** | "Experience the next frontier of hyper-intelligent AI workflows..." wastes vertical space and insults the user's intelligence. | **Terse, technical copy.** Use data badges, status indicators, and direct action verbs. |
| **Emojis in UI Labels, Buttons & Badges** | Emojis (🚀, 🔥, ✨, 🧠, ⚡, 🎉) look inconsistent across OSes, distract from data, and look unprofessional. | **Clean SVG icons only** (`singularity/static/icons/*.svg` or inline stroke SVGs with `viewBox="0 0 24 24"`). |
| **Default Browser Popups (`alert()`, `confirm()`, `prompt()`)** | Native browser dialogs freeze the thread, look atrocious, and break immersion. | **Custom Glassmorphic Toast Notification System** (`showToast()`) and custom modal confirmation overlays. |
| **Native `<select>` Dropdowns** | Native OS select boxes look completely different on Android, Windows, macOS, and Linux, with zero search capability. | **Custom Popover Select Component** (`.custom-select-wrapper`) with built-in search filter and keyboard handling. |
| **Default Blue Tap Highlight on Mobile** | Mobile WebKit draws an ugly semi-transparent blue flash over buttons on touch. | Global `-webkit-tap-highlight-color: transparent !important;` enforced on all interactive elements. |
| **Generic Circular Spinners** | A spinning wheel conveys zero progress and feels slow. | **Thematic Motion Graphic Loaders**: Neural pulse orbit for reasoning, dot matrix shimmer for images, radar scanlines for video. |

---

## 🎨 3. Color Architecture & Design Tokens

All projects share this unified CSS token architecture. (In Singularity, reference [`singularity/static/tokens.css`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/static/tokens.css)).

### 3.1 Dark Mode (Default Theme)
```css
[data-theme="dark"], :root {
  /* Surfaces */
  --bg-primary:         #151515;       /* App background, deep warm obsidian */
  --bg-secondary:       #1b1b1b;       /* Sidebar, card headers */
  --bg-surface:         #21201f;       /* Standard cards, panels, inputs */
  --bg-surface-hover:   #282726;       /* Hover states for rows and cards */
  --bg-elevated:        #2d2b29;       /* Modals, popovers, active tabs */
  --bg-input:           #191817;       /* Inset input backgrounds */
  --bg-glass:           rgba(21, 21, 21, 0.88); /* Backdrop filter surface */

  /* Warm Stone Borders */
  --border-subtle:      #2b2826;       /* Standard card and panel dividing lines */
  --border-medium:      #3d3936;       /* Hovered borders, active card borders */
  --border-strong:      #524d49;       /* Focused inputs, active triggers */
  --border-focus:       var(--brand-primary);

  /* Typography */
  --text-primary:       #ede9e3;       /* Crisp warm white, high contrast */
  --text-secondary:     #a8a29e;       /* Neutral muted text for descriptions */
  --text-muted:         #78716c;       /* Low-contrast metadata, shortcuts, timestamps */
  --text-inverse:       #151515;       /* Text on solid brand-colored buttons */

  /* Shadows */
  --shadow-sm:          0 1px 2px rgba(0, 0, 0, 0.35);
  --shadow-md:          0 4px 12px rgba(0, 0, 0, 0.45);
  --shadow-lg:          0 8px 24px rgba(0, 0, 0, 0.55);
}
```

### 3.2 Light Mode (Clean Warm Linen)
```css
[data-theme="light"] {
  --bg-primary:         #fcfcfb;       /* Warm alabaster canvas */
  --bg-secondary:       #f5f4f1;       /* Light stone sidebar */
  --bg-surface:         #ffffff;       /* Pure white elevated cards */
  --bg-surface-hover:   #f9f8f6;       /* Soft warm hover */
  --bg-elevated:        #ffffff;       
  --bg-input:           #f7f6f3;       
  --bg-glass:           rgba(252, 252, 251, 0.92);

  --border-subtle:      #e7e5e1;       
  --border-medium:      #d6d3ce;       
  --border-strong:      #a8a29e;       

  --text-primary:       #1c1917;       
  --text-secondary:     #57534e;       
  --text-muted:         #8c857f;       
  --text-inverse:       #ffffff;       
}
```

### 3.3 Core Brand & Semantic Accents
```css
:root {
  /* Signature Terracotta Brand Accent */
  --brand-primary:      #d97757;       /* Signature terracotta primary (adaptable per project brand) */
  --brand-hover:        #c86646;       
  --brand-active:       #b75536;       
  --brand-light:        #f5ece8;       
  --brand-glow:         rgba(217, 119, 87, 0.22);
  --brand-subtle:       rgba(217, 119, 87, 0.10);

  /* Status Colors (Semantic) */
  --color-success:        #10b981;     /* Active daemons, valid tokens, 200 OK */
  --color-success-bg:     rgba(16, 185, 129, 0.12);
  --color-success-border: rgba(16, 185, 129, 0.28);

  --color-warning:        #f59e0b;     /* Rate limits, simulation mode warning */
  --color-warning-bg:     rgba(245, 158, 11, 0.12);
  --color-warning-border: rgba(245, 158, 11, 0.28);

  --color-error:          #ef4444;     /* Dead workers, quota exhaustion, 500 errors */
  --color-error-bg:       rgba(239, 68, 68, 0.12);
  --color-error-border:   rgba(239, 68, 68, 0.28);

  --color-info:           #3b82f6;     /* Informational toasts, link references */
  --color-info-bg:        rgba(59, 130, 246, 0.12);
  --color-info-border:    rgba(59, 130, 246, 0.28);
}
```

### 3.4 Provider Color Signature Map
Each AI provider has an official brand color assigned strictly to its icon, badge, and card accent:

| Provider | Brand Color Hex | Background Tint | Badge Label |
| :--- | :--- | :--- | :--- |
| **ChatGPT** | `#10a37f` | `rgba(16, 163, 127, 0.12)` | `OpenAI` |
| **Claude** | `#d97706` | `rgba(217, 119, 6, 0.12)` | `Anthropic` |
| **Gemini** | `#1a73e8` | `rgba(26, 115, 232, 0.12)` | `Google DeepMind` |
| **Kimi** | `#00C389` | `rgba(0, 195, 137, 0.12)` | `Moonshot AI` |
| **GLM** | `#4f46e5` | `rgba(79, 70, 229, 0.12)` | `Zhipu AI` |
| **Grok** | `#1d9bf0` | `rgba(29, 155, 240, 0.12)` | `xAI` |
| **DeepSeek** | `#0066FF` | `rgba(0, 102, 255, 0.12)` | `DeepSeek AI` |
| **Qwen** | `#615CED` | `rgba(97, 92, 237, 0.12)` | `Alibaba Cloud` |

---

## 📐 4. Typography & Numerical Density

All applications employ this dual-typeface system designed for rapid scanning and technical legibility:

```css
--font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', Menlo, Monaco, Consolas, monospace;
```

### When to Use Which Font:
- **`--font-sans` (Plus Jakarta Sans)**: Main application navigation, card titles, button copy, descriptions, markdown prose, chat messages.
- **`--font-mono` (JetBrains Mono)**:
  - Model IDs (e.g., `kimi-k3-thinking`, `deepseek-reasoner`, `qwen3.8-max`)
  - Server ports (e.g., `8086`, `9000`)
  - Latencies (e.g., `91.0 ms`, `478.2 ms`)
  - Token counts and quotas (e.g., `50 / 50`, `3 / 3 hrs`)
  - Timestamps, IDs, JSON keys, API paths (`/v1/chat/completions`)

### Scale Hierarchy
| Token | REM | Pixels | Usage |
| :--- | :--- | :--- | :--- |
| `--font-size-xs` | `0.75rem` | 12px | Badges, tags, port indicators, table metadata |
| `--font-size-sm` | `0.875rem` | 14px | Buttons, input labels, table cell content |
| `--font-size-base` | `0.9375rem` | 15px | Chat bubble prose, body copy |
| `--font-size-md` | `1.0625rem` | 17px | Sidebar brand title, card header titles |
| `--font-size-lg` | `1.25rem` | 20px | Main section headers |
| `--font-size-xl` | `1.5rem` | 24px | Modal titles, primary stat numbers |
| `--font-size-2xl` | `1.875rem` | 30px | Hero dashboard metrics |

---

## 🎛️ 5. Component Blueprint: Custom Dropdown System

Native `<select>` elements are strictly prohibited. The custom popover component guarantees identical rendering, search-filtering, and keyboard accessibility across all platforms.

```
┌───────────────────────────────────────────────┐
│  Selected Model: kimi-k3-thinking         ▼   │  <- .custom-select-trigger
└───────────────────────────────────────────────┘
        │
        ▼ (on click)
┌───────────────────────────────────────────────┐
│ 🔍 [ Filter models...                       ] │  <- .select-search-input
├───────────────────────────────────────────────┤
│ kimi-k3-thinking (Moonshot AI)            ✓   │  <- .select-option.selected
│ deepseek-v4-pro (DeepSeek AI)                 │  <- .select-option
│ qwen3.8-max (Alibaba Cloud)                   │  <- .select-option
│ gpt-5-6-mini (OpenAI)                         │  <- .select-option
└───────────────────────────────────────────────┘  <- .custom-select-popover
```

### HTML Structure
```html
<div class="custom-select-wrapper" id="playground-model-select">
  <div class="custom-select-trigger" id="model-select-trigger" tabindex="0">
    <span class="trigger-label">Select Model</span>
    <svg class="chevron-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </div>
  <div class="custom-select-popover" id="model-select-popover">
    <div class="select-search-box">
      <input type="text" class="select-search-input" placeholder="Filter models..." />
    </div>
    <div class="select-options-list">
      <!-- Dynamically populated .select-option nodes -->
    </div>
  </div>
</div>
```

### CSS Requirements
- `.custom-select-wrapper`: `position: relative; user-select: none; min-width: 220px;`
- `.custom-select-trigger`: `border-radius: var(--radius-md); padding: 9px 14px; background: var(--bg-input); border: 1px solid var(--border-subtle);`
- Active state border: `border-color: var(--brand-primary);`
- `.custom-select-popover`: `position: absolute; top: calc(100% + 6px); background: var(--bg-surface); border: 1px solid var(--border-medium); border-radius: var(--radius-md); box-shadow: var(--shadow-lg); z-index: 100; max-height: 280px; overflow-y: auto;`
- Dismissal: Listens for outside clicks and `Escape` key event.

---

## 🔔 6. Component Blueprint: Toast Notification System

Native `alert()`, `confirm()`, and `prompt()` calls are **strictly forbidden**. All system feedback flows through the glassmorphic toast stack.

### HTML Container
Placed once at the root of `index.html`:
```html
<div id="toast-container"></div>
```

### Styling
```css
#toast-container {
  position: fixed;
  top: 20px;
  right: 24px;
  z-index: 99999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md);
  padding: 12px 18px;
  box-shadow: var(--shadow-lg);
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 280px;
  max-width: 420px;
  animation: toastIn 200ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  transition: all var(--transition-fast);
}

.toast.toast-success { border-left: 4px solid var(--color-success); }
.toast.toast-error   { border-left: 4px solid var(--color-error); }
.toast.toast-info    { border-left: 4px solid var(--brand-primary); }
```

### JS Implementation API
```javascript
// Example invocation
showToast('All 8 providers online with live telemetry.', 'success', 3500);
showToast('Quota depleted on account. Auto-failing over...', 'warning', 4000);
showToast('Failed to connect to gateway port 9000.', 'error', 5000);
```

---

## 🔘 7. Component Blueprint: Buttons & Micro-Interactions

Buttons strictly adhere to the **No-Pill Rule**:

```css
/* Base Button Geometry */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: var(--font-size-sm);
  font-weight: 600;
  font-family: var(--font-sans);
  border-radius: var(--radius-md); /* 8px - NEVER 9999px / rounded-full */
  border: 1px solid transparent;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  transition: all var(--transition-fast);
  -webkit-tap-highlight-color: transparent !important;
  outline: none;
}

/* Micro-Interaction Click Compression */
.btn:active {
  transform: scale(0.98);
}

/* 1. Primary Action Button */
.btn-primary {
  background-color: var(--brand-primary);
  color: #ffffff;
  border-color: var(--brand-primary);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}
.btn-primary:hover {
  background-color: var(--brand-hover);
  border-color: var(--brand-hover);
}

/* 2. Secondary Outline / Surface Button */
.btn-secondary {
  background-color: var(--bg-surface);
  color: var(--text-primary);
  border-color: var(--border-medium);
}
.btn-secondary:hover {
  background-color: var(--bg-surface-hover);
  border-color: var(--border-strong);
}

/* 3. Destructive / Danger Button */
.btn-danger {
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error-border);
}
.btn-danger:hover {
  background-color: var(--color-error);
  color: #ffffff;
}

/* 4. Compact Icon Action Button */
.btn-icon {
  width: 34px;
  height: 34px;
  padding: 0;
  border-radius: var(--radius-sm); /* 6px */
}
```

---

## ⚡ 8. Component Blueprint: Motion Graphic Loaders

Generic spinning circular wheels are banned across all projects. Applications must use **thematic motion graphic loaders** tailored to query modalities:

### 8.1 Reasoning & Thinking Loader (`.text-thinking-loader`)
- Used for `kimi-k3-thinking`, `deepseek-reasoner`, `qwen-thinking`, `o3-mini`.
- **Motion**: Dual-concentric orbital rings pulsing with glowing nodes and a step-by-step progress timer.
- Accompanied by the collapsible `<div class="reasoning-box">` displaying live thought tokens in dimmed font.

### 8.2 Image Generation Loader (`.image-gen-loader`)
- Used for image models (e.g. `dall-e-3`, `flux-1.1-pro`, `qwen-image`).
- **Motion**: ChatGPT-style glowing dot matrix shimmer across an aspect-ratio locked frame (1:1, 16:9, etc.).

### 8.3 Video Generation Loader (`.video-gen-loader`)
- Used for video models (e.g. `sora-2`, `grok-video`, `qwen-video`).
- **Motion**: Cinematic 16:9 frame with radar sweep scanlines and frame counter indicator.

---

## 🖼️ 9. Interactive Media Cards & Lightbox Modal

When images or videos are generated, raw base64 data strings are **never dumped onto the screen**. They are dynamically extracted and rendered into interactive cards:

```
┌───────────────────────────────────────────────┐
│                                               │
│             [ Rendered Image ]                │
│          (Hover: "Click to Expand")           │
│                                               │
├───────────────────────────────────────────────┤
│ [IMAGE] [1:1]         [⤢ Expand]  [📋 Copy]   │ <- .media-card-toolbar
└───────────────────────────────────────────────┘
```

- **Hover Overlay**: Dark glass overlay with expand icon.
- **Toolbar Actions**: Lightbox zoom modal, 1-click clipboard copy, and download action with model-tagged filenames (`singularity-<model>-<timestamp>.png`).
- **Lightbox Modal**: Fixed viewport glass overlay (`.lightbox-modal`) with zoom-to-fit, full-res download, and backdrop click dismissal.

---

## 📐 10. Layout System & 100dvh Lock

All desktop and web applications enforce a rigid layout container to prevent double scrollbars:

```css
/* Master Viewport Lock */
html, body {
  height: 100%;
  width: 100%;
  overflow: hidden;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

#app {
  display: flex;
  height: 100dvh;
  width: 100vw;
  overflow: hidden;
}

/* Sidebar Navigation */
.sidebar {
  width: 270px;
  min-width: 270px;
  height: 100%;
  background-color: var(--bg-secondary);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
}

/* Main Content Area */
.main-content {
  flex: 1;
  height: 100%;
  overflow-y: auto;
  padding: 32px 40px;
}
```

### High-Density Grid Structure
- **Models Catalog**:
  ```css
  .models-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 18px;
    width: 100%;
  }
  ```
- **Playground View**:
  ```css
  .playground-layout {
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: 24px;
    height: calc(100dvh - 120px);
    min-height: 500px;
  }
  ```

---

## 🧩 11. SVG Iconography Standards

1. **Pure Vectors Only**: All icons must be pure SVG. External font libraries (FontAwesome, Material Icons ligatures) are strictly forbidden to eliminate Flash of Unstyled Text (FOUT) and layout shifts.
2. **Standard Stroke Syntax**:
   ```html
   <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
     <!-- Path coordinates -->
   </svg>
   ```
3. **Brand & Service Logos**:
   - Stored as pure vectors in the project's static assets directory (e.g. `static/icons/*.svg`).
   - Must be clean, normalized to 24x24 or 32x32 viewBox, and styled with semantic accent colors.

---

## 📝 12. Markdown & Code Rendering Standards

Inside the Playground chat stream, incoming markdown is formatted on the fly via `renderMarkdown()`:

1. **Syntax Highlighting**: Code blocks are wrapped with language tags (`.code-block-header`) and equipped with a 1-click `Copy Code` button that turns into `✓ Copied!` for 2 seconds.
2. **Tables**: Markdown tables automatically receive `.chat-table-wrapper` with horizontal scroll containment and subtle striped rows (`:nth-child(even)`).
3. **Reasoning Box (`.reasoning-box`)**:
   - Collapsible thinking tray placed above assistant bubbles.
   - Distinctive border (`border-left: 2px solid var(--border-medium)`).
   - Dimmed monospace font (`var(--text-muted)`) to clearly distinguish thoughts from final answers.
4. **Empty Bubble Protection**: If a stream terminates with pure reasoning or an error, `parseAndRenderMediaContent()` guarantees a fallback state (`Thinking process complete.`) so bubbles never collapse to 0px height.

---

## ✅ 13. UI Review Checklist for Any Project or PR

Before shipping frontend code in any project, verify against this 10-point checklist:

- [ ] **No Pill Buttons**: Are all button border-radii set to 6px or 8px? (Zero instances of `border-radius: 9999px` or `rounded-full` on buttons).
- [ ] **No Overdone Gradients**: Are all surfaces flat or subtle glass? Are borders clean 1px solid warm stone?
- [ ] **No Native Selects**: Are all model and provider selectors using `.custom-select-wrapper`?
- [ ] **No Native Alerts**: Is every notification dispatched through `showToast(msg, type)`?
- [ ] **Full Viewport Utilization**: Does the view scale to 100% of the available width on desktop screens?
- [ ] **Zero Unnecessary Subtitles**: Is all copy concise, technical, and free of marketing fluff?
- [ ] **No Floating Emojis**: Are all icons implemented as crisp, stroke-based SVGs?
- [ ] **100dvh Lock**: Does the body remain locked with zero window-level scroll bouncing?
- [ ] **Dark & Light Mode Tested**: Do all CSS tokens resolve cleanly under both `[data-theme="dark"]` and `[data-theme="light"]`?
- [ ] **Touch Highlight Disabled**: Is `-webkit-tap-highlight-color: transparent` active on all interactive items?
