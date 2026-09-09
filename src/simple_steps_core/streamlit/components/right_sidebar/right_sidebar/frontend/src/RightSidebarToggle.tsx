import React, { useEffect, useRef, useState } from "react"
import {
  ComponentProps,
  Streamlit,
  withStreamlitConnection,
} from "streamlit-component-lib"

/**
 * Streamlit's default themes don't expose their colors as CSS variables, so
 * we derive a "secondary background" shade (matching the look of the native
 * sidebar) from the app's actual background color and publish it as a CSS
 * variable the panel's stylesheet can read.
 */
function syncThemeColors(): { background: string; text: string } | null {
  const parentDoc = window.parent.document
  const appEl = parentDoc.querySelector<HTMLElement>(".stApp")
  if (!appEl) {
    return null
  }
  const appStyle = getComputedStyle(appEl)
  const bg = appStyle.backgroundColor
  const match = bg.match(/\d+/g)
  if (!match) {
    return null
  }
  const [r, g, b] = match.map(Number)
  const luminance = (r * 299 + g * 587 + b * 114) / 1000
  const shift = luminance < 128 ? 24 : -18
  const clamp = (n: number): number => Math.min(255, Math.max(0, n))
  const secondary = `rgb(${clamp(r + shift)}, ${clamp(g + shift)}, ${clamp(
    b + shift
  )})`
  parentDoc.documentElement.style.setProperty(
    "--right-sidebar-bg",
    secondary
  )
  return { background: secondary, text: appStyle.color }
}

/**
 * A small pill-shaped handle with a chevron, used to collapse/expand the
 * right sidebar. Rendered outside the collapsing panel so it always stays
 * clickable, regardless of the panel's current state.
 */
function RightSidebarToggle({ args }: ComponentProps): React.ReactElement {
  const collapsed = Boolean(args["collapsed"])
  const rootRef = useRef<HTMLDivElement>(null)
  const [theme, setTheme] = useState({ background: "#ffffff", text: "#31333f" })

  const icon: string | undefined = args["icon"]
  const collapseIcon: string | undefined = args["collapseIcon"]
  const expandIcon: string | undefined = args["expandIcon"]
  const customIcon = (collapsed ? expandIcon : collapseIcon) ?? icon

  // Loads Google's Material Symbols font once (shared across component reruns)
  // so `:material/<name>:` shortcodes render as real icons.
  useEffect(() => {
    const id = "right-sidebar-material-symbols"
    if (document.getElementById(id)) return
    const link = document.createElement("link")
    link.id = id
    link.rel = "stylesheet"
    link.href =
      "https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined"
    document.head.appendChild(link)
  }, [])

  // Runs on every render (no deps) so it re-checks the parent theme on
  // every Streamlit rerun, not just when `collapsed` changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const colors = syncThemeColors()
    if (
      colors &&
      (colors.background !== theme.background || colors.text !== theme.text)
    ) {
      setTheme(colors)
    }
  })

  useEffect(() => {
    if (rootRef.current) {
      Streamlit.setFrameHeight(rootRef.current.scrollHeight)
    }
  })

  const handleClick = (): void => {
    Streamlit.setComponentValue(!collapsed)
  }

  return (
    <div ref={rootRef} style={{ display: "flex", justifyContent: "flex-end" }}>
      <button
        onClick={handleClick}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        style={{
          width: 40,
          height: 40,
          padding: 0,
          border: "none",
          borderRadius: "50%",
          background: theme.background,
          color: theme.text,
          opacity: 0.6,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/* Double chevron, matching Streamlit's own sidebar collapse/expand icon. */}
        {customIcon ? (
          <span style={{ fontSize: 22, lineHeight: 1 }}>
            {renderIconString(customIcon)}
          </span>
        ) : (
          // Double chevron, matching Streamlit's own sidebar collapse/expand icon.
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{
              transform: collapsed ? "rotate(180deg)" : "none",
              transition: "transform 150ms ease-in-out",
            }}
          >
            <polyline points="6 18 12 12 6 6" />
            <polyline points="13 18 19 12 13 6" />
          </svg>
        )}
      </button>
    </div>
  )
}

// Replaces Streamlit-style `:material/<name>:` shortcodes with Material Symbol
// spans; leaves other text (emoji, plain characters) untouched. Also accepts
// the common typo `:materials/<name>:`.
function renderIconString(value: string): React.ReactNode {
  const parts = value.split(/(:materials?\/[a-z0-9_]+:)/gi)
  return parts.map((part, i) => {
    const match = part.match(/^:materials?\/([a-z0-9_]+):$/i)
    if (match) {
      return (
        <span
          key={i}
          className="material-symbols-outlined"
          style={{ fontSize: "inherit", verticalAlign: "middle" }}
        >
          {match[1]}
        </span>
      )
    }
    return <React.Fragment key={i}>{part}</React.Fragment>
  })
}

export default withStreamlitConnection(RightSidebarToggle)
