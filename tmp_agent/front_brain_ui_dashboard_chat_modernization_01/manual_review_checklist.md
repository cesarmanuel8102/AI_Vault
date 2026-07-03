# Phase 5 — Manual Review Checklist

Front: `FRONT-BRAIN-UI-DASHBOARD-CHAT-MODERNIZATION-01`

No automated screenshot capability. Operator should open `http://127.0.0.1:8092/` in a browser and verify each item.

## Dashboard

- [ ] Page loads with "Brain Operator Console" title in top bar.
- [ ] Top status bar shows: Brain API, Dashboard, Backend, Provider, READ-ONLY, MEM LOCKED, TRADING LOCKED, Autonomy, last refresh.
- [ ] Left navigation shows 9 items: Overview, Agent, Chat, Tools, Memory, Traces, Safety, Ops, Roadmap.
- [ ] Clicking each nav item swaps the main content view (hash changes in URL).
- [ ] Overview renders 9 cards with live data (Service Health, Agent V2, Capabilities, Recent Runs, Provider, Safety Locks, Memory, Promotion Queue, Dashboard EPs).
- [ ] Overview "What Brain is Doing Now" shows state/cycle/last run.
- [ ] Agent view shows backend (langgraph_parity), runtime type, provider, run count.
- [ ] Safety view shows all locks as LOCKED (blue) by default.
- [ ] Ops view shows 8091 LIVE, 8092 LIVE, 8070 INACTIVE, runbook path, disabled control buttons.
- [ ] Top bar refresh indicator updates every ~10s.

## Chat

- [ ] Chat view shows 3-column layout: sidebar, main conversation, right inspector.
- [ ] Empty state visible ("Start a conversation").
- [ ] Type a message → press Enter → user bubble appears (right, accent color).
- [ ] Loading state shows during request.
- [ ] Assistant bubble appears (left) with markdown rendered.
- [ ] Code blocks show with copy button on hover (click copies, shows ✓).
- [ ] Shift+Enter inserts newline (no send).
- [ ] Right inspector updates: run id, classification, model/provider, mode, blocked tools, trace link.
- [ ] Mode badge READ_ONLY visible in composer.
- [ ] "New chat" button clears the conversation.

## States

- [ ] If provider degraded: yellow warning strip under assistant message.
- [ ] If fallback used: orange warning strip.
- [ ] If backend unreachable: red error bubble with guidance.
- [ ] If network drops: top bar shows "✕ offline".

## Safety

- [ ] No enabled stop/restart/commit/trading/memory-write buttons anywhere.
- [ ] Ops control buttons are disabled with tooltips ("requires future approved backend front").
- [ ] Sidebar conversation list shows "NOT CONNECTED" placeholder.
- [ ] Tools view shows "NOT CONNECTED" placeholder.

## Responsive

- [ ] Narrow window (<820px): sidebar collapses, inspector hides, top bar chips reduce.
- [ ] Chat layout remains usable on narrow width.

## Markdown / code

- [ ] Send a prompt asking for a code block → response renders fenced code with styling + copy button.
- [ ] Bold/italic/headers render correctly in assistant bubbles.
- [ ] Inline code shows with accent background.

## Remaining UI gaps (known, deferred)

- Conversation history not persisted (no backend) — placeholder shown.
- Live tool registry list — endpoint not exposed.
- Live service controls — disabled (require approved backend front).
- Branch/head display — endpoint not exposed.
