# Prospero’s Study

A quiet writing room with a hint of the theatre. The name is **Prospero’s Study** in display copy and **Prospero's Study** in plain-text/browser metadata.

## Identity

- **Emblem:** a fountain-pen nib inside a proscenium arch, with a short stage line. Keep it static, with clear space; avoid masks, curtains, ornamental scripts, or extra effects.
- **Wordmark:** Literata Regular, gently tightened. IBM Plex Sans remains the interface face; IBM Plex Mono remains for technical details.
- **Ink:** `#191816`; **parchment:** `#ede5d6`; **brass:** `#c5a46d`. Brass identifies actions, focus, and selection. All six existing reading palettes remain available.
- **Voice:** welcoming and literary. Keep functional names such as Write, Stories, Library, Settings, and Roleplay. The theatrical language belongs in small identity details.

## Assets

- `public/brand/study-mark.svg`: transparent, font-free UI mark; used by `StudyMark` with a decorative empty alt. Its enclosing control supplies the accessible name.
- `public/favicon.svg`: high-contrast, rounded browser tile.
- `public/favicon.ico`: 16, 32, and 48 px fallback.
- `public/brand/app-icon.svg`: square master with extra breathing room for operating-system rounding.
- `public/brand/icon-192.png`, `public/brand/icon-512.png`: app icon exports.
- `public/apple-touch-icon.png`: 180 px touch icon.
- `public/site.webmanifest`: browser/app identity metadata. No offline capability is implied.

The pen-and-arch paths in the three SVG variants share the same geometry. Use the vector originals for future exports. Preserve the background on browser/app tiles so the mark stays legible on light and dark chrome.

Branding does not migrate storage keys, archive formats, provider headers, environment variables, or the launcher health identifier. Those retain their existing compatibility names.
