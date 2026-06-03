# Yield Scanner

Projeto didatico em Python para monitorar oportunidades de yield DeFi via DeFiLlama e variacoes de preco via CoinGecko.

**Stack:** Python 3.12 + SQLite + requests + PyYAML

> Este projeto e uma base white-label para estudo. Ele nao executa ordens, nao movimenta fundos e nao e recomendacao financeira.

---

## O Que Este App Faz

- Busca pools de yield na API publica da DeFiLlama.
- Filtra pools por chain, ativos, TVL minimo e APY minimo.
- Salva historico local em SQLite.
- Detecta oportunidades/anomalias de APY.
- Monitora preco de ativos configurados via CoinGecko.
- Gera relatorio diario simples.
- Opcionalmente envia notificacoes via Telegram.

---

## Instalar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Uso Rapido

```bash
# Scan de yields e gravacao no SQLite
python scanner_cli.py scan

# Analise de anomalias APR/APY no banco local
python scanner_cli.py apr

# Monitoramento de preco
python scanner_cli.py prices

# Relatorio diario
python scanner_cli.py report

# Pipeline completo: scan -> apr -> prices
python scanner_cli.py full

# Simular sem gravar estado
python scanner_cli.py scan --dry-run

# Emitir JSON ao final do stdout
python scanner_cli.py scan --json
```

O comando `apr` depende de um `scan` anterior, porque ele le os dados salvos em `data/defillama_yields.db`.

---

## Exit Codes

| Codigo | Significado |
|--------|-------------|
| 0 | Sucesso, sem alertas |
| 1 | Erro recuperavel, normalmente API indisponivel |
| 2 | Erro fatal, normalmente config invalida |
| 3 | Sucesso, mas com alertas detectados |

---

## Configuracao

### `config/assets.yaml`

Define os ativos usados no monitor de precos.

```yaml
assets:
  btc:
    id: bitcoin
    symbol: BTC
    name: Bitcoin
    monitor: true
    alert_threshold_pct: 5.0
```

O campo `id` deve ser o ID usado pela CoinGecko.

### `config/telegram.yaml`

As credenciais sao lidas de variaveis de ambiente:

```yaml
telegram:
  bot_token_env: TELEGRAM_BOT_TOKEN
  chat_id_env: TELEGRAM_CHAT_ID
  enabled: true
```

Exemplo:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="123456789"
```

Se as variaveis nao estiverem definidas, as notificacoes aparecem apenas no stdout.

---

## Estrutura

```text
yield-scanner/
├── scanner_cli.py           # Entrypoint unificado
├── defillama_scanner.py     # Scanner de yields DeFiLlama
├── apr_scanner.py           # Analise de anomalias APR/APY
├── price_monitor.py         # Alertas de variacao de preco
├── daily_report.py          # Relatorio diario
├── requirements.txt
├── config/
│   ├── assets.yaml
│   ├── pools.yaml
│   └── telegram.yaml
└── src/
    ├── config.py
    ├── notifier.py
    └── state.py
```

Arquivos criados em runtime:

```text
data/
├── defillama_yields.db
└── prices.json
```

---

## Exercicios Sugeridos

1. Adicionar um novo ativo em `config/assets.yaml`.
2. Alterar os filtros de chain, TVL e APY em `defillama_scanner.py`.
3. Trocar os thresholds de alerta em `apr_scanner.py`.
4. Criar uma notificacao customizada usando `src/notifier.py`.
5. Exportar as top oportunidades para CSV.

---

## Reset Local

```bash
# Reset historico de yields
rm data/defillama_yields.db

# Reset estado de precos
rm data/prices.json
```

---

## Troubleshooting

**`apr` retorna poucas ou nenhuma pool**

Execute `python scanner_cli.py scan` antes. O `apr` usa o banco SQLite local.

**CoinGecko retorna 429**

E rate limit. Aguarde e rode novamente. O codigo ja possui retry simples.

**Telegram nao envia**

Confira `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Sem essas variaveis, o app usa stdout.
