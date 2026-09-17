export function artworkUrl(digest: string, size = 'display') {
  return `/api/library-artwork/${encodeURIComponent(digest)}?size=${size}`
}
