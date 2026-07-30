# 005 — Add Accelerated CSS Spinner for Form Submission Feedback

- **Status**: TODO
- **Commit**: HEAD
- **Severity**: LOW
- **Category**: Missed opportunities
- **Estimated scope**: 2 files (`static/style.css`, `static/js/ux_optimization.js`)

## Problem

In `static/js/ux_optimization.js`, form submission button feedback replaces innerHTML with raw emoji text: `<span class="inline-block animate-spin mr-2">⏳</span> Processing...`. Without a matching CSS `@keyframes` spin animation in `static/style.css`, the emoji remains static or renders inconsistently across browsers.

Current code excerpt (`static/js/ux_optimization.js:142`):

```javascript
if (submitBtn.tagName === 'BUTTON') {
    submitBtn.innerHTML = '<span class="inline-block animate-spin mr-2">⏳</span> Processing...';
}
```

## Target

Add a GPU-accelerated CSS spinner component `.btn-spinner` and update `ux_optimization.js` to utilize an inline SVG / CSS spinner.

```css
/* target in static/style.css */
.btn-spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: currentColor;
    border-radius: 50%;
    animation: btnSpin 600ms linear infinite;
    vertical-align: middle;
    margin-right: 6px;
}

@keyframes btnSpin {
    to { transform: rotate(360deg); }
}
```

```javascript
/* target in static/js/ux_optimization.js */
if (submitBtn.tagName === 'BUTTON') {
    submitBtn.innerHTML = '<span class="btn-spinner"></span> Processing...';
}
```

## Repo conventions to follow

- Utility animations are placed at the bottom of `static/style.css`.

## Steps

1. In `static/style.css`, add `.btn-spinner` and `@keyframes btnSpin` rules.
2. In `static/js/ux_optimization.js` line 142, update the innerHTML template from emoji `⏳` to `<span class="btn-spinner"></span> Processing...`.

## Boundaries

- Do NOT alter form submission prevention or timeout handling logic.

## Verification

- **Mechanical**: Submit any form on the page.
- **Feel check**: Observe submit button state change to a smooth rotating loading ring.
- **Done when**: Form submit button displays continuous, GPU-accelerated 600ms linear rotation during submission.
