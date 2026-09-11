# Design Read

Use this contract before implementing a **new surface, redesign, or material visual-direction change**. It turns a vague aesthetic request into a testable frontend direction.

A narrow bugfix or small refinement should preserve the incumbent world and does not need a new Design Read.

## Required shape

```yaml
design_read:
  subject: "What the product/surface is really about"
  audience:
    primary: "Who uses it"
    context: "Where/why/how they use it"
  primary_job: "The one job this surface must make easier"
  intent: persuade | operate | read | experience
  surface: marketing | product | data-dense | motion | figma | architecture | validation

  authority:
    primary: "user | project-design-system | figma | incumbent-product"
    advisory:
      - "optional specialist/reference"

  direction:
    pov: "A concrete visual point of view tied to subject/audience/job"
    memorable_move: "The single most characteristic visual/interaction move"

  dials:
    variance: 1-10
    motion: 1-10
    density: 1-10

  preserve:
    - "flows/URLs/copy/components that must not change"

  avoid:
    - "project-specific failure modes or generic defaults to avoid"
```

## Rules

- The primary job is behavioral, not aesthetic.
- `authority.primary` must name existing evidence; advisory sources never outrank it.
- `pov` must be specific enough to reject plausible alternatives.
- `memorable_move` is one deliberate focal idea, not a list of effects.
- Dials are relative guidance, not permission to violate accessibility/performance.
- `avoid` should be brief and contextual. Do not turn anti-patterns into a universal banned-style list.

## Uniqueness check

Before implementation, substitute an unrelated product into the read.

If the direction still works unchanged, revise the weak parts. Common weak answers are “modern SaaS,” “premium minimal,” “clean dashboard,” or any direction justified only by trend/fashion.

A strong read can answer: **why does this decision belong to this subject, audience, and job?**
