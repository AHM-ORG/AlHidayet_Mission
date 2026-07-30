# 006 — Apple Fluid Interface & Physical Motion Enhancements

- **Status**: TODO
- **Commit**: HEAD
- **Severity**: HIGH
- **Category**: Physicality & Easing (Apple Design)
- **Estimated scope**: 2 files (`static/style.css`, `templates/dashboard.html`)

## Problem

The UI components currently lack Apple-style fluid physical feedback. Buttons and cards do not offer instant pointer-down press feedback (`transform: scale(0.97)` on `:active`), floating headers lack translucent depth (`backdrop-filter`), and modal/drawer entrances lack Apple's signature fluid response curve (`cubic-bezier(0.16, 1, 0.3, 1)` and `cubic-bezier(0.32, 0.72, 0, 1)`).

Current code excerpt (`static/style.css:163` & `2094`):

```css
/* Button active state without direct 1:1 scale feedback */
.btn {
    transition: color var(--transition), background var(--transition), box-shadow var(--transition), transform var(--transition);
}

/* Modal scaling without Apple fluid response curve */
.review-modal-content {
    transform: scale(0.92) translateY(24px);
    transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

## Target

Implement Apple Fluid interface design standards:

1. **Instant Pointer-Down Feedback**:
```css
.btn:active, .dash-card:active, .custom-card:active {
    transform: scale(0.97) !important;
    transition: transform 100ms cubic-bezier(0.23, 1, 0.32, 1) !important;
}
```

2. **Apple Translucent Materials (`backdrop-filter`)**:
```css
.header, .top-bar, .modal-header {
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
}
```

3. **Apple Fluid Response Tokens**:
```css
:root {
    --ease-apple-fluid: cubic-bezier(0.16, 1, 0.3, 1);
    --ease-apple-drawer: cubic-bezier(0.32, 0.72, 0, 1);
    --ease-apple-spring: cubic-bezier(0.175, 0.885, 0.32, 1.15);
}
```

## Repo conventions to follow

- High-leverage motion utilities live at the top/root of `static/style.css`.
- Translucent overlays pair with light borders (`1px solid rgba(255, 255, 255, 0.4)`).

## Steps

1. In `static/style.css`, add `--ease-apple-fluid`, `--ease-apple-drawer`, and `--ease-apple-spring` to `:root`.
2. Add `:active` physical touch response rules for `.btn`, `.dash-card`, and interactive cards.
3. Update `.top-bar` and floating headers with `backdrop-filter: blur(20px) saturate(180%);`.
4. Update modal dialog scale entrance to use `transform: scale(0.96) translateY(10px)` with `--ease-apple-fluid`.

## Boundaries

- Do NOT add heavy JavaScript dependencies.
- Ensure `backdrop-filter` falls back gracefully for legacy browsers.

## Verification

- **Mechanical**: Inspect computed styles of `.btn:active` and `.top-bar` in browser DevTools.
- **Feel check**:
  - Click and hold any button: feedback must appear instantly on pointer-down (`scale(0.97)`).
  - Open modals: motion should emulate native iOS sheet/modal fluid physics.
- **Done when**: All interactive elements respond to pointer-down instantly with hardware-accelerated fluid transitions.
