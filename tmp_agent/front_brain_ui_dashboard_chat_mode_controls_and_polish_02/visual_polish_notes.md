# Phase 4 — Visual Polish Notes

Front: `FRONT-BRAIN-UI-DASHBOARD-CHAT-MODE-CONTROLS-AND-POLISH-02`

## Mode selector (restored + professional)

- Segmented control `[📖 READ] [🔨 BUILD] [⚙ AUTO]` rendered in a single row directly above the textarea inside the composer — visible without scrolling.
- Active button: accent border + inset glow + accent text. Inactive: muted text, hover lifts to panel background.
- Each button carries a small subtitle (`read-only` / `approval-gated` / `governance-enforced`) and a tooltip with the safety label.
- Helper text under the composer: "Mode selection does not bypass governance. Writes, memory mutation, trading and commits remain locked unless backend explicitly requires and receives approval."

## Composer

- Mode badge in the actions row now reflects the **selected** mode (READ_ONLY / BUILD / AUTO) and updates live when the user clicks a segment.
- Chat status line (bottom right of composer) shows the selected mode when idle, "Thinking…" when busy.
- Nav footer mode badge also updates to the selected mode.

## Message thread

- Assistant messages widened to 94% max-width so they read as a workspace column, not a small floating card.
- User messages keep right alignment at 86% with a small gray mode tag at the bottom of the bubble (READ / BUILD / AUTO) so the operator can see what mode was active when the message was sent.
- Empty state updated: mentions mode selection and that governance is enforced regardless.

## Conversation sidebar

- Placeholder restyled: dashed border, "Session" label, "In-memory only · not persisted" — reads as an intentional design choice, not a broken feature.

## Inspector

- Run Inspector card now has: Run ID, Classification, Model/Provider, **Mode Requested**, **Mode Effective**, **Auto Decision**.
- New **Escalation / Approval** card appears only when `mode_escalation_required === true`: shows reason, required permission, expected write scope, confirmation ID, and a note that no write was executed.
- Cards remain scannable with consistent label/value typography.

## Top bar

- Status chips preserved. Safety locks (MEM LOCKED, TRADING LOCKED, READ-ONLY) remain visible.
- Nav footer mode badge reflects selected chat mode.

## Fallback clarity (FIX-6)

- "Fallback used: none" false-alarm removed — warning strip now only appears when `fallback_reason` is truthy AND not the literal string `none`/empty.

## Responsive

- Mode selector remains a single row at laptop width (flex:1 distributes evenly).
- On narrow width (<820px) the inspector and sidebar collapse; the mode selector stays in the composer.
