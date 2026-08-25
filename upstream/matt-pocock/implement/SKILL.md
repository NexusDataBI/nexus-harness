---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

# patched: Nexus guardrail v3.2 — sem commit automático
Não commitar. Aguardar instrução explícita do Rubens para qualquer commit.
Antes de encerrar, verificar checklist obrigatório Nexus:
- Código toca auth/DB/input/secrets/webhook? → acionar security-reviewer antes de reportar pronto.
- Código tem SQL/migration/schema? → acionar database-reviewer antes de reportar pronto.
- Ao concluir a implementação, rodar verification-loop antes de reportar pronto.
