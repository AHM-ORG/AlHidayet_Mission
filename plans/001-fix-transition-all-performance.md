# 001 — Eliminate `transition: all` for Hardware-Accelerated Performance

- **Status**: TODO
- **Commit**: HEAD
- **Severity**: HIGH
- **Category**: Performance
- **Estimated scope**: 3 files (`static/style.css`, `templates/application_form.html`, `templates/dashboard.html`)

## Problem

Multiple UI elements across `static/style.css` and HTML templates use `transition: all`. Animating `all` forces the browser's layout engine to recalculate non-composite properties (such as `width`, `height`, `margin`, `padding`, and `border-color`) on every frame, causing main-thread frame drops during scrolling and interaction.

Current code excerpts:

```css
/* static/style.css:1553 — toast notifications */
.toast-notification {
    transition: all 400ms cubic-bezier(0.16, 1, 0.3, 1);
}

/* static/style.css:1591 — toast close button */
.toast-close-btn {
    transition: all 200ms ease;
}

/* static/style.css:1957 — general override */
.custom-card {
    transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1) !important;
}

/* templates/application_form.html:64 & 83 — form inputs & buttons */
.form-control, .btn-submit {
    transition: all 0.3s;
}

/* templates/dashboard.html:66 — dashboard widgets */
.dash-card {
    transition: all 0.3s ease;
}
```

## Target

Explicitly list GPU-accelerated transition properties (`transform`, `opacity`) along with color/background properties. Eliminate all `transition: all` declarations.

```css
/* static/style.css:1553 */
.toast-notification {
    transition: transform 260ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)),
                opacity 260ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1));
}

/* static/style.css:1591 */
.toast-close-btn {
    transition: background-color 160ms ease-out,
                color 160ms ease-out,
                opacity 160ms ease-out;
}

/* static/style.css:1957 */
.custom-card {
    transition: transform 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)),
                box-shadow 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)),
                border-color 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)) !important;
}

/* templates/application_form.html:64 & 83 */
.form-control {
    transition: border-color 180ms ease-out, box-shadow 180ms ease-out;
}

/* templates/dashboard.html:66 */
.dash-card {
    transition: transform 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)),
                box-shadow 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1));
}
```

## Repo conventions to follow

- Easing and motion variables live in `:root` inside `static/style.css`.
- Keep duration under 300ms for UI components.

## Steps

1. In `static/style.css`, locate `.toast-notification` at line 1553 and replace `transition: all 400ms cubic-bezier(0.16, 1, 0.3, 1);` with `transition: transform 260ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)), opacity 260ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1));`.
2. In `static/style.css`, locate `.toast-close-btn` at line 1591 and replace `transition: all 200ms ease;` with `transition: background-color 160ms ease-out, color 160ms ease-out, opacity 160ms ease-out;`.
3. In `static/style.css`, locate line 1957 and replace `transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1) !important;` with `transition: transform 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)), box-shadow 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)), border-color 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)) !important;`.
4. In `templates/application_form.html`, locate line 64 and replace `transition: all 0.3s;` with `transition: border-color 180ms ease-out, box-shadow 180ms ease-out;`.
5. In `templates/dashboard.html`, locate line 66 and replace `transition: all 0.3s ease;` with `transition: transform 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1)), box-shadow 200ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1));`.

## Boundaries

- Do NOT change markup or class names.
- Do NOT remove existing color or background values.

## Verification

- **Mechanical**: Load `templates/dashboard.html` and `templates/application_form.html` in browser DevTools. Inspect `.toast-notification` and `.dash-card` in computed styles to ensure `transition-property` is explicit and not `all`.
- **Feel check**:
  - Trigger toast notifications and hover dashboard cards.
  - Confirm movement is smooth and non-stuttering.
- **Done when**: `grep_search` for `transition: all` returns no instances in CSS / templates.
