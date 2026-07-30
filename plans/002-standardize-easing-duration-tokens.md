# 002 — Standardize Easing and Duration CSS Tokens

- **Status**: TODO
- **Commit**: HEAD
- **Severity**: HIGH
- **Category**: Easing & duration
- **Estimated scope**: 1 file (`static/style.css`)

## Problem

The design system currently relies on a single generic `--transition: 180ms cubic-bezier(.2, .8, .2, 1);` token, while scattered components use uncurated easings like `ease`, `ease-in-out`, or overly long durations (e.g. `fadeUp 520ms` and `620ms`).

Current code excerpt (`static/style.css:26`):

```css
:root {
    --transition: 180ms cubic-bezier(.2, .8, .2, 1);
}
```

And lines 437, 519:

```css
.card-header {
    animation: fadeUp 520ms var(--transition) both;
}

.card-body {
    animation: fadeUp 620ms var(--transition) 80ms both;
}
```

## Target

Introduce standardized, high-leverage motion tokens in `:root` based on Kowalski's motion hierarchy:

```css
:root {
    --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
    --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
    --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
    --duration-fast: 150ms;
    --duration-normal: 220ms;
    --duration-slow: 300ms;
    --transition: var(--duration-fast) var(--ease-out);
}
```

And trim excessive entrance animations to stay under the 300ms budget:

```css
.card-header {
    animation: fadeUp var(--duration-normal) var(--ease-out) both;
}

.card-body {
    animation: fadeUp var(--duration-slow) var(--ease-out) 40ms both;
}
```

## Repo conventions to follow

- All CSS tokens are declared in `:root` at the top of `static/style.css`.

## Steps

1. In `static/style.css`, expand line 26 under `:root` to include:
   `--ease-out: cubic-bezier(0.23, 1, 0.32, 1);`
   `--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);`
   `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);`
   `--duration-fast: 150ms;`
   `--duration-normal: 220ms;`
   `--duration-slow: 300ms;`
   `--transition: var(--duration-fast) var(--ease-out);`
2. Update `.card-header` animation at line 437 to use `var(--duration-normal) var(--ease-out)`.
3. Update `.card-body` animation at line 519 to use `var(--duration-slow) var(--ease-out) 40ms`.

## Boundaries

- Do NOT rename existing CSS variable names (`--transition`).
- Keep all UI durations under 300ms.

## Verification

- **Mechanical**: Inspect `:root` variables in DevTools to ensure `--ease-out`, `--ease-in-out`, etc. are defined.
- **Feel check**: Reload the dashboard. Cards should enter briskly and feel instantly interactive without sluggish lag.
- **Done when**: Keyframe animations complete within 300ms total elapsed time.
