# Design Language

The visual system for the Job Offer Matcher frontend. It sits on top of **Angular
Material 3** — Material owns the brand/surface/neutral color roles and the type
scale; this layer adds the semantic colors, scales, and reusable patterns Material
doesn't give a name to, and documents the conventions that keep every page coherent.

> **One rule above all:** never hard-code a hex value in a component. Reach for a
> `--mat-sys-*` role (brand/structure) or an `--app-*` token (status/scale). The only
> file allowed to contain raw status hex is `src/styles/_tokens.scss`.

## Where things live

| File | Role | Imported |
| --- | --- | --- |
| `src/styles.scss` | Material theme, base elements, `.page` / `.page-header` | app entry |
| `src/styles/_tokens.scss` | `:root` design tokens (color, spacing, radius, elevation, motion) | once, by `styles.scss` |
| `src/styles/_mixins.scss` | Pattern mixins (`accent-card`, `avatar`, `status-badge`) | per-component, via `@use 'mixins' as m` |
| `src/styles/_utilities.scss` | Global helper classes + the single `spin` keyframes | once, by `styles.scss` |

`stylePreprocessorOptions.includePaths` (in `angular.json`) is set to `src/styles`,
so any component SCSS can `@use 'mixins' as m;` with a flat name.

## Principles

1. **Calm canvas, scarce accent.** Surfaces are neutral; the brand violet is reserved
   for *actions* (primary buttons, active nav, links). Following 60-30-10, the accent
   is ~10% of any view — that scarcity is what makes "this is clickable" legible.
2. **Color carries meaning.** A matching product uses color semantically: cyan =
   AI/insight/highlight, green = success/match strength, amber = caution, red = error.
3. **Tokens, not magic numbers.** Spacing and radius come from scales so rhythm is
   consistent and global tweaks are one-line.
4. **Accessible by default.** Material's tonal palettes pair on-colors to hit WCAG
   contrast automatically; our semantic tokens are tuned to clear **AA (4.5:1 text,
   3:1 UI)** on app surfaces. Never signal state with color alone — pair an icon/text.
5. **Dark mode is free.** The root sets `color-scheme: light dark`; Material tokens and
   our `light-dark()` tokens both resolve to it, so the app follows the OS preference.

## Color

### Brand & structure — use Material roles

`--mat-sys-primary` (violet, actions), `--mat-sys-tertiary` (cyan, highlight),
`--mat-sys-secondary`, `--mat-sys-surface` / `-container-*`, `--mat-sys-on-surface[-variant]`,
`--mat-sys-outline-variant`, `--mat-sys-error`.

### Status — use app tokens (adapt for dark mode)

| Token | Meaning | Soft-tint pair |
| --- | --- | --- |
| `--app-success` | success / strong match | `--app-success-container` |
| `--app-warning` | caution / medium match | `--app-warning-container` |
| `--app-info` | AI / insight (aliases tertiary) | `--app-info-container` |
| `--app-danger` | error (aliases `--mat-sys-error`) | — |
| `--app-rating` | star ratings (amber) | — |

### The `--accent` convention

Tinted cards and their avatars are colored by a single `--accent` custom property the
element sets, so a section card and its leading avatar always share one color:

```scss
@use 'mixins' as m;

.section { @include m.accent-card; }      // left rail + faint wash of --accent
.section--experience { --accent: var(--app-success); }
.section-avatar { @include m.avatar; }     // round filled badge in the same --accent
```

## Scales

- **Spacing** (`--app-space-1..7`): `4 · 8 · 12 · 16 · 24 · 32 · 48` px.
- **Radius** (`--app-radius-*`): `sm 8` · `md 12` (cards) · `lg 16` · `pill 999`.
- **Elevation** (`--app-shadow-1`, `--app-shadow-2`).
- **Motion** (`--app-ease`, `--app-duration` 160ms, `--app-duration-fast` 120ms).
  `.spin` is disabled under `prefers-reduced-motion`.

## Typography

Roboto via Material's type scale. Headings use scale tokens, not ad-hoc sizes:
`h1` → `headline-small`, `h2` → `title-large`, `h3` → `title-medium` (all 600 weight).
Body is `--mat-sys-body-medium`. Prefer `font: var(--mat-sys-*)` over raw `font-size`.

## Reusable patterns

- **`.page`** — the centered content column every route sits in (`styles.scss`).
- **`.page-header`** — accent banner with icon + title + hint; color via `--page-accent`.
- **`accent-card` / `avatar` / `status-badge`** mixins — the building blocks above.
- **`.app-card-accent` / `.app-avatar` / `.app-status-block`** — class versions for
  templates that want the pattern without a component-scoped rule.

## Checklist for new UI

- [ ] No raw hex — use a `--mat-sys-*` role or an `--app-*` token.
- [ ] Spacing/radius from the scales.
- [ ] Brand violet only on actionable elements.
- [ ] Status shown with icon **and** color.
- [ ] Text contrast ≥ 4.5:1, UI/icons ≥ 3:1 — checked in **both** light and dark.
- [ ] Tinted card? `@include m.accent-card` + set `--accent`, don't re-roll the recipe.
