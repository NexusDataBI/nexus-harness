# Nexus Project Memory

Canonical durable engineering memory for this repository.

This directory stores verified project knowledge as Markdown plus JSON sidecars.
Git is the history. Derived indexes are disposable. Obsidian is an optional UI,
not the database.

## Layout

```text
.nexus/memory/
├── README.md
├── decisions/
├── invariants/
├── components/
├── patterns/
├── lessons/
└── incidents/
```

Each memory is a pair: `<id>.md` for humans and `<id>.json` for machines.
Do not treat `index.json` or search databases as source of truth.

## Rules

- Persist only durable engineering facts, never secrets or raw credentials.
- Prefer current repository truth, approved specs and fresh evidence over memory.
- Only `VERIFIED` memories are eligible for automatic recall.
- Do not delete unknown files in this tree; they may be local notes.
