---
name: subagent-driven-development
description: Use when tackling complex tasks that can be broken into independent subtasks. Trigger when the user asks to implement a large feature, refactor multiple files, build something with distinct components, or any task where parallel execution with review checkpoints would be more effective than sequential work. Also trigger on mentions of subagents, parallel tasks, task decomposition for AI agents, or multi-step implementations.
---

# Subagent-Driven Development

## Purpose
Break complex tasks into independent subtasks executed by focused subagents, with code review checkpoints between iterations. This produces better results than monolithic implementations because each subtask gets full attention and context.

## When to Use This Pattern

- Feature requires changes across 3+ files/modules
- Task has clearly separable concerns (frontend + backend + database)
- Implementation benefits from incremental review (catch issues early)
- Task is too complex for a single pass without losing quality

## Workflow

### Phase 1: Decomposition
1. **Analyze the full requirement**
2. **Identify independent subtasks** — each should be testable on its own
3. **Define clear interfaces** between subtasks (data contracts, API shapes)
4. **Order by dependency** — which subtasks must complete before others can start?
5. **Present the plan** to the user for approval before executing

### Phase 2: Execution with Checkpoints
For each subtask:
1. **State the subtask goal** clearly
2. **Implement it completely** (including tests)
3. **Self-review checkpoint:**
   - Does this subtask meet its specification?
   - Does it integrate correctly with previously completed subtasks?
   - Are there edge cases missing?
   - Is the code clean and well-documented?
4. **Present the result** to the user
5. **Incorporate feedback** before moving to the next subtask

### Phase 3: Integration
1. **Verify all subtasks work together**
2. **Run the full test suite**
3. **Integration test** the complete feature
4. **Final review** of the combined implementation

## Decomposition Template

```markdown
## Task: [Feature Name]

### Subtask 1: [Name] (no dependencies)
- **Goal:** [What this subtask produces]
- **Input:** [What it receives]
- **Output:** [What it delivers]
- **Tests:** [How to verify it works]
- **Estimated complexity:** Low / Medium / High

### Subtask 2: [Name] (depends on: Subtask 1)
- **Goal:** ...
- **Input:** Output from Subtask 1
- **Output:** ...
- **Tests:** ...

### Integration: 
- **Verify:** All subtasks connected correctly
- **Test:** End-to-end scenario
```

## Review Checkpoint Checklist

At each checkpoint, verify:
- [ ] Subtask goal is met completely (not partially)
- [ ] Code follows project conventions and architecture patterns
- [ ] Tests cover happy path + edge cases + error cases
- [ ] No hardcoded values that should be configurable
- [ ] Error handling is present and meaningful
- [ ] No security issues introduced (apply VibeSec checks)
- [ ] Changes don't break existing functionality
- [ ] Code is documented where non-obvious

## Anti-Patterns to Avoid

- **Over-decomposition:** Don't split a 20-line function into 5 subtasks
- **Hidden dependencies:** If subtask 3 secretly depends on subtask 2's internals, the decomposition is wrong
- **Skipping checkpoints:** The whole point is incremental quality control
- **Premature integration:** Don't try to wire things together until each piece works independently
