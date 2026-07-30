# 003 — Refactor Reduced Motion Media Query for Accessibility

- **Status**: TODO
- **Commit**: HEAD
- **Severity**: MEDIUM
- **Category**: Accessibility
- **Estimated scope**: 1 file (`static/style.css`)

## Problem

The reduced-motion media query currently forces all animations and transitions to `1ms !important`. This brute-force removal strips user feedback completely (such as background color changes on focus/hover or opacity fades) and causes jarring visual state pops for users who need reduced motion due to vestibular disorders.

Current code excerpt (`static/style.css:1396-1404`):

```css
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        scroll-behavior: auto !important;
        animation-duration: 1ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 1ms !important;
    }
}
```

## Target

Keep opacity and color feedback intact while eliminating heavy spatial shifts (`transform: translateY(...)`, `scale(...)`):

```css
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        scroll-behavior: auto !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 150ms !important;
    }

    /* Disable spatial movement while retaining opacity feedback */
    .toast-notification,
    .review-modal-content,
    .dash-card,
    [class*="fadeUp"] {
        transform: none !important;
    }
}
```

## Repo conventions to follow

- Accessibility overrides live inside the `@media (prefers-reduced-motion: reduce)` block in `static/style.css`.

## Steps

1. In `static/style.css`, locate lines 1396-1410.
2. Replace the brute-force `1ms` duration rules with `150ms` transition duration for opacity/colors and explicitly set `transform: none !important;` for spatial containers.

## Boundaries

- Do NOT completely disable transition opacity or color feedback.
- Do NOT alter standard non-reduced motion queries.

## Verification

- **Mechanical**: Enable `prefers-reduced-motion: reduce` in browser DevTools (Rendering tab).
- **Feel check**:
  - Open modals or toast alerts; verify that position doesn't jump or slide across screen, but opacity fades gracefully.
- **Done when**: Reduced motion mode smoothly fades elements without spatial displacement.
