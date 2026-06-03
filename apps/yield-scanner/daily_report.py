#!/usr/bin/env python3
"""
Daily Report
Relatório diário dos assets monitorizados via CoinGecko.

Uso:
  python daily_report.py
  python daily_report.py --dry-run

Exit codes:
  0 = Sucesso
"""

import sys
import time
import requests
import argparse
from datetime import datetime, timezone
from typing import List

from src.config import load_assets
from src.state import get_state

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
MAX_RETRIES = 3
RETRY_DELAY = 5

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def fetch_prices(asset_ids: List[str]) -> dict:
    ids_csv = ",".join(asset_ids)
    params = {
        "ids": ids_csv,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            log(f"CoinGecko request: {ids_csv} (tentativa {attempt + 1}/{MAX_RETRIES})")
            resp = requests.get(COINGECKO_URL, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                log(f"Rate limit (429), aguardando {RETRY_DELAY}s...", "WARN")
                time.sleep(RETRY_DELAY)
            else:
                log(f"HTTP Error {resp.status_code}: {e}", "ERROR")
                raise
        except Exception as e:
            log(f"Erro: {e}", "ERROR")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise
    
    raise Exception("Falha após todas as tentativas")

def build_daily_report(dry_run=False) -> List[str]:
    log("=== DAILY REPORT ===")
    log(f"Modo: {'DRY-RUN' if dry_run else 'PRODUÇÃO'}")
    
    assets_cfg = load_assets()
    assets = assets_cfg.get("assets", {})
    asset_ids = [v["id"] for v in assets.values()]
    
    log(f"Assets no relatório: {list(assets.keys())}")
    
    data = fetch_prices(asset_ids)
    state = get_state("prices")
    
    lines = [
        f"📊 Daily Report — Yield Scanner",
        f"🕘 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    
    for symbol, cfg in assets.items():
        coin_id = cfg["id"]
        if coin_id not in data:
            log(f"Sem dados para {coin_id}", "WARN")
            lines.append(f"• {symbol.upper()}: dados indisponíveis")
            continue
        
        price = data[coin_id]["usd"]
        change_24h = data[coin_id].get("usd_24h_change", 0)
        prev = state.get(coin_id)
        
        diff_str = ""
        if prev:
            diff_pct = ((price - prev) / prev) * 100
            diff_str = f" | vs ciclo anterior: {diff_pct:+.2f}%"
            log(f"{cfg['symbol']}: ${price:,.2f} (24h: {change_24h:+.2f}%, vs anterior: {diff_pct:+.2f}%)")
        else:
            log(f"{cfg['symbol']}: ${price:,.2f} (24h: {change_24h:+.2f}%)")
        
        lines.append(
            f"• <b>{symbol.upper()}</b>: ${price:,.2f}  (24h: {change_24h:+.2f}%){diff_str}"
        )
    
    lines.append("")
    lines.append("— Fim do relatório —")
    
    log("")
    log("=== RELATÓRIO GERADO ===")
    for line in lines:
        log(line)
    
    return lines

def main():
    parser = argparse.ArgumentParser(description="Daily Report")
    parser.add_argument("--dry-run", action="store_true", help="Simula execução")
    args = parser.parse_args()
    
    build_daily_report(dry_run=args.dry_run)
    sys.exit(0)

if __name__ == "__main__":
    main()
