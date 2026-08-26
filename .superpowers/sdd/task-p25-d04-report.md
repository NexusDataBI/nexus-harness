# P25-D04 — Relatório

## Status

Concluído na branch `feat/v4-memory`.

## Implementação

- `session_recall` usa carregamento tolerante quando chamado pelo fluxo de sessão.
- Sidecars com JSON inválido, objeto incompleto, enum inválido, erro de tipo ou I/O são excluídos individualmente.
- A cápsula mantém `findings` estruturados e adiciona avisos sem incluir valores do payload.
- Memórias válidas continuam elegíveis para HOT/WARM; o carregador estrito permanece intacto para doctor e APIs existentes.
- `docs/migration/debt.json`: P25-D04 atualizado para `resolved`.

## Evidência TDD

- RED: `PYTHONPATH=src python3 -m unittest tests.test_memory_session -v`
  falhou nos três novos cenários com `KeyError`/`ValueError`, reproduzindo a causa.
- GREEN focado: 6 testes de sessão passaram.
- GREEN obrigatório focado: 28 testes passaram (`session`, `store`, `integration`).
- GREEN obrigatório completo: 228 testes passaram via `unittest discover`.
- Lint IDE: nenhum erro nos arquivos alterados.

## Commits

- `b1b161c` — checkpoint RED dos testes.
- Commit de implementação: `fix: fail-soft session recall on schema-invalid memory`.
