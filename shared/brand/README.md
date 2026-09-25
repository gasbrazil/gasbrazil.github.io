# GasBrazil brand files

Master logo files. The full usage guide (colors, clear space, minimum size) lives in the GasBrazil design system.

| File | Use |
| --- | --- |
| `gasbrazil-wordmark-color.svg` | Wordmark with the color flame, for light backgrounds. |
| `gasbrazil-wordmark-color-reverse.svg` | White wordmark with the dark-mode flame, for dark backgrounds. |
| `gasbrazil-wordmark-black.svg` | One-color black, for print and documents. |
| `gasbrazil-wordmark-white.svg` | One-color white, for photos and flag-blue or green fills. |
| `gasbrazil-wordmark-color-1200.png`, `…-color-reverse-1200.png` | PNG fallbacks where SVG isn't accepted (email signatures, some social uploads). |
| `gasbrazil-flame.svg`, `gasbrazil-flame-dark.svg` | The flame on its own, light and dark versions. |
| `gasbrazil-icon-192.png`, `gasbrazil-icon-512.png` | App icons on the light page background (web manifest). |
| `og-image.png` | 1200 × 630 link-preview image. |

All SVGs are pure vector (outlined Pacaembu SemiBold plus the vector flame); no font or embedded image is needed.

## Site-wide head tags

Every page's `<head>` gets the same block from `kit.brand_head_html()` in `shared/dashboard_kit.py` (via `seo_head()` or each template's `__BRAND_HEAD__` / `{{BRAND_HEAD}}` placeholder). `shared/resync_built_shells.py` rewrites it into committed shells.

| Tag | File |
| --- | --- |
| `<link rel="icon" sizes="32x32">` | `/favicon.ico` (16, 32, 48 px) for browsers without SVG favicons |
| `<link rel="icon" type="image/svg+xml">` | `/shared/favicon.svg`: the vector flame; its blue core lightens under `prefers-color-scheme: dark` |
| `<link rel="apple-touch-icon">` | `/apple-touch-icon.png` (180 px) |
| `<link rel="manifest">` | `/site.webmanifest` with `gasbrazil-icon-192.png` and `gasbrazil-icon-512.png` |
| `og:image`, `twitter:card` / `twitter:image` | `og-image.png` (1200 × 630): the cover lockup, used for link previews. Dropped on `/admin/` (`social=False`). |

`/shared/favicon.png` (32 px) and `/favicon.png` (128 px) remain for anything that still links them directly.

The passcode screen shows the flame above the wordmark (`gasbrazil-flame.svg`, swapped for `gasbrazil-flame-dark.svg` in the dark theme), and its top stripe uses the same flag proportions and tokens as `.flagbar`.

Keep at least the height of the "a" clear around the wordmark, and don't use the flame version below 120 px wide; use the plain typeset wordmark with its accent dot there instead.
