---
name: test-driven-development
description: Use when implementing any feature, bugfix, refactor, or code change — BEFORE writing implementation code. Trigger whenever the user asks to build, implement, create, add, fix, or change any code. Also trigger on mentions of TDD, red-green-refactor, test-first, unit tests before code, or any request where writing tests first would improve the outcome.
---

# Test-Driven Development (TDD) Skill

## Purpose
Enforce the discipline of writing tests before implementation code. TDD is not about testing — it's about DESIGN. Tests written first force you to think about the API, the edge cases, and the contracts before you write a single line of implementation.

## The TDD Cycle: Red → Green → Refactor

### 🔴 RED — Write a Failing Test First
1. Write the SMALLEST possible test that describes the next behavior you need
2. The test must FAIL (if it passes, you're not testing anything new)
3. The test should be clear enough that someone reading it understands the requirement
4. Run the test. See it fail. Read the error message. This is your specification.

**Rules for the RED phase:**
- Test ONE behavior at a time. Not two. Not "a few related things." ONE.
- Name the test descriptively: `test_user_cannot_login_with_expired_token` not `test_login_3`
- The test should specify WHAT, not HOW. Test the interface, not the implementation.

### 🟢 GREEN — Make the Test Pass (Minimum Effort)
1. Write the SIMPLEST code that makes the test pass
2. It's OK if the code is ugly, hardcoded, or naive
3. Do NOT add functionality the test doesn't require
4. Run all tests. Everything must pass.

**Rules for the GREEN phase:**
- Resist the urge to write "proper" code. That's the next phase.
- If you're writing more than a few lines, the test was too big. Go back to RED with a smaller test.
- Don't refactor yet. Don't add error handling the test doesn't require. Just pass the test.

### 🔵 REFACTOR — Clean Up Without Changing Behavior
1. Now improve the code: remove duplication, extract functions, rename variables, improve structure
2. Run tests after EVERY change. If anything breaks, revert the last change.
3. Apply SOLID principles, design patterns, and clean code practices
4. Also refactor the tests: remove duplication, improve readability

**Rules for the REFACTOR phase:**
- Tests must stay green through the entire refactoring process
- No new functionality. Only structural improvements.
- If you want new behavior, go back to RED.

## TDD Workflow in Practice

### Step 1: Understand the requirement
Before writing any test, clarify:
- What is the input?
- What is the expected output/behavior?
- What are the edge cases?
- What are the error cases?

### Step 2: Make a test list
Write a checklist of all the behaviors you need to implement:
```
## Test List for: User Registration
- [ ] Valid registration with all required fields
- [ ] Rejects duplicate email
- [ ] Rejects password shorter than 8 characters
- [ ] Rejects invalid email format
- [ ] Hashes password before storing
- [ ] Returns user ID on success
- [ ] Sends welcome email on success
```

### Step 3: Start with the simplest test
Pick the easiest test from the list. Implement RED → GREEN → REFACTOR. Then pick the next one.

### Step 4: Grow complexity gradually
Each test should add ONE new constraint or behavior. The implementation grows organically.

## Test Quality Guidelines

### Good Tests Are:
- **Fast:** Milliseconds, not seconds. No real databases, no network calls, no file I/O.
- **Isolated:** Each test can run independently, in any order.
- **Repeatable:** Same result every time. No randomness, no time-dependency.
- **Self-validating:** Pass or fail. No manual inspection needed.
- **Timely:** Written BEFORE the code, not after.

### Test Structure (Arrange-Act-Assert):
```
def test_discount_applies_for_orders_over_100():
    # Arrange — Set up the test scenario
    order = Order(items=[Item(price=120)])
    calculator = PriceCalculator(discount_threshold=100, discount_rate=0.1)
    
    # Act — Execute the behavior under test
    total = calculator.calculate(order)
    
    # Assert — Verify the expected outcome
    assert total == 108.0  # 120 - 10% discount
```

### What to Test vs What NOT to Test
**DO test:**
- Business logic and rules
- Edge cases and boundary values
- Error handling and validation
- State transitions
- Public API contracts

**DO NOT test:**
- Private methods directly (test them through public methods)
- Framework/library internals
- Trivial getters/setters
- Implementation details that might change

## Mocking Strategy

- **Mock external dependencies:** databases, APIs, file systems, clocks
- **Don't mock the thing you're testing**
- **Don't mock value objects** — use real ones
- **Prefer fakes over mocks** when the dependency is simple
- **If you need more than 3 mocks in a test,** the code under test has too many dependencies → refactor first

## When TDD Feels Hard

| Situation | Likely Problem | Solution |
|-----------|---------------|----------|
| Can't write the first test | Requirement is unclear | Clarify the requirement before coding |
| Test is too complex to write | The feature is too big | Break it into smaller increments |
| Need many mocks | Too many dependencies | Apply Dependency Inversion, extract interfaces |
| Tests are slow | Testing through real I/O | Use in-memory implementations, fakes |
| Tests break on every refactor | Tests couple to implementation | Test behavior (WHAT), not structure (HOW) |

## Response Format

When implementing features with TDD:

1. **Start by listing the test cases** (the test list)
2. **Write the first failing test** with a clear explanation
3. **Write the minimal passing implementation**
4. **Refactor if needed**
5. **Move to the next test**
6. **Repeat until all behaviors are covered**

Always show the test BEFORE the implementation. Never show implementation without a corresponding test.
