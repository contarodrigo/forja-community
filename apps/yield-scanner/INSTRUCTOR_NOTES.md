# Instructor Notes

Esta versao white-label foi preparada para alunos.

## Pontos Para Explicar Em Aula

- Separacao entre coleta de dados, persistencia, analise e notificacao.
- Uso de APIs publicas com retry e timeout.
- Persistencia local com SQLite e JSON.
- Configuracao por YAML e variaveis de ambiente.
- Exit codes para automatizar pipelines.

## Sequencia Recomendada

1. Rodar `python scanner_cli.py scan --dry-run` para mostrar logs sem gravar estado.
2. Rodar `python scanner_cli.py scan` para criar `data/defillama_yields.db`.
3. Rodar `python scanner_cli.py apr` para mostrar como a analise usa o DB local.
4. Rodar `python scanner_cli.py prices` para criar `data/prices.json`.
5. Alterar `config/assets.yaml` e repetir o fluxo.

## Cuidados

- O app nao executa trades.
- Os dados sao de APIs publicas e podem falhar ou sofrer rate limit.
- APY alto pode indicar risco, incentivo temporario ou erro de dado.
- A pasta `data/` deve ficar fora do material base se voce quiser entregar um estado limpo.

## Ideias De Extensao

- Dashboard web simples.
- Exportacao CSV.
- Ranking por risco/retorno.
- Suporte a mais chains.
- Testes unitarios para filtros e thresholds.
