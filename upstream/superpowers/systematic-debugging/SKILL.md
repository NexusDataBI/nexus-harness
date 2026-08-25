---
name: systematic-debugging
description: Use when encountering any bug, test failure, unexpected behavior, error message, or crash — BEFORE proposing fixes. Also trigger when the user says something "doesn't work", "is broken", "gives an error", reports a regression, or asks "why is this happening". This skill enforces a structured debugging methodology instead of guessing at solutions.
---

# Systematic Debugging Skill

## Purpose
Prevent the #1 debugging anti-pattern: jumping to conclusions and making random changes hoping something sticks. This skill enforces a disciplined process of observation → hypothesis → verification → fix.

## The Golden Rule
**NEVER propose a fix until you understand the root cause.** If you can't explain WHY the bug exists, you don't understand it well enough to fix it.

## Debugging Workflow

### Phase 1: OBSERVE (Don't touch anything yet)

1. **Reproduce the bug:** Can you make it happen consistently? What are the exact steps?
   - If it's intermittent, note the conditions (timing, data, environment, load)
   - If you can't reproduce it, you can't verify a fix. Focus on reproduction first.

2. **Gather evidence:** Before changing code, collect ALL available information:
   - Exact error message (full stack trace, not just the summary)
   - What was the expected behavior vs actual behavior?
   - When did it last work correctly? What changed since then? (`git log`, `git diff`)
   - Environment details: OS, language version, dependency versions, config
   - Logs: application logs, server logs, browser console, network tab

3. **Define the boundary:** Where does the bug live?
   - Which layer? (UI, API, business logic, database, infrastructure)
   - Which module/file/function?
   - Binary search: if the system has 10 steps, does step 5 produce correct output? Narrow the search space by half each time.

### Phase 2: HYPOTHESIZE (Think before you act)

4. **Form hypotheses:** Based on evidence, list possible causes ranked by likelihood:
   ```
   Hypothesis 1 (most likely): [description] — Evidence: [what supports this]
   Hypothesis 2: [description] — Evidence: [what supports this]
   Hypothesis 3: [description] — Evidence: [what supports this]
   ```

5. **Design a test for each hypothesis:** How would you PROVE or DISPROVE each one?
   - What specific observation would confirm the hypothesis?
   - What observation would rule it out?
   - Can you test it without modifying production code? (logging, debugger, REPL)

### Phase 3: VERIFY (Test one thing at a time)

6. **Test hypotheses in order:** Start with the most likely. Change ONE variable at a time.
   - If you change multiple things, you won't know which one fixed it
   - Use print/log debugging, breakpoints, or unit tests to verify

7. **Follow the data:** Let the evidence guide you, not your assumptions.
   - If hypothesis 1 is disproven, don't force it. Move to hypothesis 2.
   - If none of your hypotheses hold, go back to Phase 1 and gather more evidence.

### Phase 4: FIX (Now you can change code)

8. **Implement the minimal fix:** Fix the root cause, not the symptoms.
   - Ask: "Am I fixing WHY it happens, or just WHERE it happens?"
   - A fix at the symptom level will break again in a different way.

9. **Verify the fix:**
   - Does the original reproduction case now pass?
   - Do all existing tests still pass?
   - Write a new test that specifically covers this bug (regression test)
   - Check for similar patterns elsewhere in the codebase (same bug, different location?)

10. **Document:**
    - What was the root cause?
    - Why did the previous code behave incorrectly?
    - What was changed and why?
    - How can this category of bug be prevented in the future?

## Common Bug Categories & Diagnostic Approaches

### State Bugs
- **Symptoms:** Works sometimes, fails other times. Order-dependent.
- **Approach:** Log state at each transition point. Look for race conditions, shared mutable state, missing initializations.

### Timing/Async Bugs
- **Symptoms:** Intermittent failures. "Works on my machine." Fails under load.
- **Approach:** Add timestamps to logs. Look for missing awaits, unhandled promises, race conditions, timeout assumptions.

### Data Bugs
- **Symptoms:** Wrong output for specific inputs. Works for some data, fails for others.
- **Approach:** Identify the minimal failing input. Compare with a working input. What's different? Check edge cases: null, empty, unicode, very large, negative, boundary values.

### Integration Bugs
- **Symptoms:** Works in isolation, fails when connected. API contract mismatches.
- **Approach:** Log request/response at integration boundaries. Compare expected vs actual payloads. Check API versioning, serialization format, auth tokens.

### Environment Bugs
- **Symptoms:** Works locally, fails in staging/production.
- **Approach:** Diff configurations. Check env vars, dependency versions, file paths, permissions, network access, DNS, TLS certificates.

## Red Flags — When Debugging Goes Wrong

Stop and reassess if you notice:
- You've been debugging for >30 minutes without new evidence → Take a break, explain the bug to someone (rubber duck)
- You're making random changes to see what happens → Go back to Phase 1
- Your fix requires changing 10+ files → You might be fixing a symptom. Find the root cause.
- The fix works but you can't explain WHY → You don't understand the bug. Keep investigating.
- You're fixing a fix → The first fix was wrong. Revert and start over.

## Response Format for Debugging

When helping debug an issue, structure the response as:

```
## Bug Analysis

**Observed behavior:** [what's happening]
**Expected behavior:** [what should happen]
**Evidence collected:** [error messages, logs, stack traces]

## Hypotheses (ranked by likelihood)
1. [Most likely cause] — Supporting evidence: [...]
2. [Alternative cause] — Supporting evidence: [...]

## Diagnostic Steps
1. [First thing to check/test]
2. [Second thing to check/test]

## Root Cause (after investigation)
[Explanation of WHY the bug exists]

## Fix
[Minimal change that addresses the root cause]

## Regression Test
[Test case that ensures this specific bug doesn't return]

## Prevention
[How to prevent this category of bug in the future]
```
