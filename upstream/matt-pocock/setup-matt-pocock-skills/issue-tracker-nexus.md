# Issue tracker: Nexus (markdown local)

Specs, planos aprovados e tickets deste repo vivem em markdown. Não criar um tracker paralelo ao que o repo já usa.

## Precedência

1. Repo com `.specs/` (SDD) → specs em `.specs/`; planos aprovados em `docs/plans/`
2. Repo com `docs/plans/` → specs/planos em `docs/plans/`; tickets em `.scratch/<feature>/issues/`
3. Default → tickets em `.scratch/<feature>/issues/`; criar `docs/plans/` se precisar persistir um plano aprovado

## Convenções Nexus

- Napkin do repo: `.claude/napkin.md` (runbook, não log)
- Deploy profile: `.claude/deploy-profile.md` (obrigatório para `/deploy`)
- AGENTS.md / CLAUDE.md **local** sobrescreve o global; este setup só edita o do repo
- `research.md` é efêmero (válido pelo sprint). Preferir `.scratch/<feature>/research.md` e não promover ao vault
- Prototype é throwaway — a decisão vai para a spec; o código do protótipo não vira produção

## Tickets

- Um arquivo por ticket: `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numerados a partir de `01`
- Nunca um único arquivo combinando todos os tickets
- Fatia vertical (schema + API + UI + teste no mesmo ticket), ≤ 500 linhas de lógica
- `Blocked by:` lista os tickets que gateiam este; `Status:` usa o vocabulário de `triage-labels.md`
- Comentários no final, sob `## Comments`

## Specs e planos

- Plano aprovado: `docs/plans/AAAA-MM-DD-<slug>.plan.md` (ou `.specs/` se o repo for SDD)
- Spec gerada por `/to-spec`: no tracker acima, não em `.scratch/` se o repo já tem `docs/plans/` ou `.specs/`
- `/plan` Nexus (aprovação explícita do Rubens) continua obrigatório antes de `/implement` em feature média+

## Quando uma skill diz "publish to the issue tracker"

Escrever no path da precedência acima. Se for ticket, usar `.scratch/<feature-slug>/issues/`.

## Quando uma skill diz "fetch the relevant ticket"

Ler o path passado pelo usuário (número, slug ou URL local).

## Wayfinding

- **Map**: `.scratch/<effort>/map.md`
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md` com `Type:` (`research`/`prototype`/`grilling`/`task`) e `Status:` (`claimed`/`resolved`)
- **Blocking**: `Blocked by: NN, NN`
- **Frontier**: arquivos open, unblocked e unclaimed; menor número primeiro
- **Claim / Resolve**: `Status: claimed` antes do trabalho; ao resolver, `## Answer` + ponteiro no map
