# CarbonX — Design System (DESIGN.md)

> HOW IT SHOULD LOOK AND FEEL. Single source of truth for visual tokens.
> The tokens below are the actual values from `tailwind.config.js` and
> `src/index.css` — do not invent new one-off colors; add a token here if one
> is needed. Update this doc in the same PR that changes visual behaviour.

## Style

Modern, premium, earthy-agri: calm **warm-white canvas**, generous whitespace,
rounded-3xl "premium card" surfaces, subtle leaf-green gradients. Professional
enough for corporate buyers, friendly enough for a farmer on a mid-range Android.

## Typography

- **Headings:** `font-manrope` (Manrope, 600/semi-bold, tracking-tight) — applied
  to all `h1…h6` via `@layer base`.
- **Body:** `font-inter` (Inter, weights 300–700) — default body font.
- **Accent/marketing display:** `font-poppins` (Poppins, 300–800).
- Fonts load from Google Fonts in `src/index.css` (include when offline
  fallbacks are needed; do not swap families silently).
- Body text color: `carbon-900` (#0F172A). Muted: `agriText-muted` (#475569),
  subtle: `agriText-subtle` (#64748B).

## Color tokens

### Brand / action
| Token | Hex | Use |
|---|---|---|
| `primary.DEFAULT` | `#16A34A` | Primary action green |
| `primary.hover` | `#15803D` | Primary hover/active |
| `primary.light` | `#22C55E` | Positive accents |
| `primary.dark` | `#14532D` | Primary pressed / dark accents |
| `profit` | `#16A34A` | Earnings/positive money |

### Forest ramp (brand-scale, 50→900)
`#ECFDF5 → #064E3B`; `forest-500 #10B981` = primary action green,
`forest-700 #047857` = headings on light/gradient, `forest-100/200` = card borders
and soft fills.

### Earth & soil
- `earth`: `#4ADE80 / #16A34A / #15803D` (vegetation identity).
- `soil`: `#A0826C / #7C6049 / #584231` (fields, soil-carbon sections).

### Sky ramp
`sky-50 #F0F9FF` … `sky-900 #0C4A6E` — water/satellite-blue accents, info panels.

### Carbon (slate scale 50→900)
Neutral text/surfaces scale from `#F8FAFC` to `#0F172A`.

### Surfaces & warmth
| Token | Hex | Use |
|---|---|---|
| `warm.white` | `#FAFAF7` | App background (body bg) |
| `warm.cream` | `#F4F4EB` | Alternate section background |
| `surface.DEFAULT` | `#F6F5EE` | Page-alt surface |
| `surface.card` | `#FFFFFF` | Cards |
| `surface.sage` | `#E9F2EA` | Soft green fill |
| `surface.muted` | `#F1F4EF` | Muted panels |

### Status / semantic
| Token | Hex | Use |
|---|---|---|
| `alert` | `#D97706` | Warnings, pending states |
| `error` | `#DC2626` | Errors, rejected |
| `badge.registry` | `#16A34A` | Registry-verified badge |
| `badge.registryDoc` | `#166534` | Registry + document badge |
| `badge.doc` | `#1D4ED8` | Document/verification blue |
| `badge.fpo` | `#D97706` | FPO symbol |
| `verifBlue` | `#1D4ED8` | "Verified" inline tags |

## Components

- **Premium card:** `.premium-card` = `bg-white`, thin `forest-100/60` border,
  `rounded-3xl`, `shadow-card`, hover `.premium-card-hover`
  (`shadow-premium` + `-translate-y-0.5`). Cards must use these classes, not
  bespoke shadow values.
- **Glass panel:** `.glass-panel` = `bg-white/85 backdrop-blur-xl` — nav/overlay
  surfaces only.
- **Gradients:** `.bg-forest-gradient` (135°, `#1B5E20 → #2E7D32 → #81C784`)
  for hero/banners; `.text-gradient-green` for display headlines; body has
  faint radial green washes (do not re-add on sections).
- **Shadows:** only `shadow-card` and `shadow-premium` unless a token is added.
- **Buttons:** primary = `forest/primary` green fill with hover `primary.hover`;
  secondary = white/surface card with border; destructive = `error`.
  Keep one primary action per view.
- **Badges:** use the `badge.*` tokens; never free-hand status colors.

## Map (Leaflet)

`src/index.css` restyles Leaflet to match: white bars, 12px radius, soft shadow,
`#FAFAF5` canvas. Any map surface must stay consistent with these overrides.

## UX requirements (non-negotiable)

- Mobile responsive (design from 360px+; the audience is phone-first).
- Always define **loading**, **empty**, and **error** states for data surfaces.
- Money and status text comes from the API — never hardcode values in the UI.
- Honest labels: fallback/sample data must show their badges (e.g.
  "SAMPLE DATA (DB offline)") — never silently cosmeticize a fallback.
- Accessible forms: visible labels, focus states, error text tied to inputs.
