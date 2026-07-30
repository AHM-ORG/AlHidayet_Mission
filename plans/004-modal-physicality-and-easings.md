# 004 — Tune Modal Dialog Physicality and Easing

- **Status**: TODO
- **Commit**: HEAD
- **Severity**: MEDIUM
- **Category**: Physicality & origin
- **Estimated scope**: 1 file (`static/style.css`)

## Problem

Modal containers like `.review-modal-content` currently use a bouncy, spring-like curve (`cubic-bezier(0.34, 1.56, 0.64, 1)`) with a `350ms` duration and `scale(0.92)` initial transform. In a crisp enterprise management application, excessive spring bounce feels sluggish and out of place.

Current code excerpt (`static/style.css:2094-2095`):

```css
.review-modal-content {
    ...
    transform: scale(0.92) translateY(24px);
    transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

## Target

Use a subtle starting scale (`scale(0.96)`) paired with the system `--ease-out` curve (`cubic-bezier(0.23, 1, 0.32, 1)`) and `220ms` duration for a crisp, responsive modal entrance.

```css
.review-modal-content {
    ...
    transform: scale(0.96) translateY(12px);
    transition: transform var(--duration-normal, 220ms) var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)),
                opacity var(--duration-normal, 220ms) var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1));
}
```

## Repo conventions to follow

- Modals center on screen, so `transform-origin: center` is correct and should be preserved.
- Leverage `--ease-out` token created in Plan 002.

## Steps

1. In `static/style.css`, locate lines 2094-2095 under `.review-modal-content`.
2. Replace `transform: scale(0.92) translateY(24px);` with `transform: scale(0.96) translateY(12px);`.
3. Replace `transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);` with `transition: transform var(--duration-normal, 220ms) var(--ease-out), opacity var(--duration-normal, 220ms) var(--ease-out);`.

## Boundaries

- Do NOT change modal backdrop backdrop-filter or opacity transition logic.

## Verification

- **Mechanical**: Inspect `.review-modal-content` transition properties in DevTools.
- **Feel check**: Click to open a modal dialog. It should pop up smoothly without bounciness or overshoot.
- **Done when**: Modal animation duration is 220ms with smooth `--ease-out` trajectory.
