# Surface intent

`nexus-frontend` classifies frontend work on two independent axes.

## Intent

| Intent | Success condition |
| --- | --- |
| `persuade` | visitor understands value, decides, and takes an action |
| `operate` | user completes a task accurately and efficiently |
| `read` | reader understands/navigates information |
| `experience` | the artifact/content itself is the primary experience |

Classify the route/surface, not the company or product as a whole.

Examples: a tool's landing page is `persuade`; its editor is `operate`; its docs are `read`.

## Surface type

| Type | Typical shape |
| --- | --- |
| `marketing` | landing/pricing/campaign |
| `product` | app shell/settings/forms/workflows |
| `data-dense` | analytics/admin/tables/monitoring |
| `motion` | interaction where motion is a first-class design decision |
| `figma` | design-to-code or code-to-Figma |
| `architecture` | component/layout architecture where visual changes are secondary |
| `validation` | rendered QA/audit surface |

## Routing rule

Intent sets the experience priority; surface type selects the specialist.

Do not let a category stereotype pick the visual style. `operate + data-dense` does not automatically mean dark mode; `persuade + marketing` does not automatically mean gradients, cards, or oversized hero typography.
