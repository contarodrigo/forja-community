#!/usr/bin/env python3
"""
Price Monitor
Monitora preços de assets via CoinGecko com retry e backoff.
Estado persistente em data/ ao invés de /tmp/.

Uso:
  python price_monitor.py
  python price_monitor.py --dry-run

Exit codes:
  0 = Sem alertas
  3 = Variações detetadas
"""

import sys
import time
import requests
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Tuple

from src.config import load_assets
from src.state import get_state

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
MAX_RETRIES = 3
RETRY_DELAY = 5

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def fetch_prices(asset_ids: List[str]) -> Dict:
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

def format_alert(asset_symbol: str, old_price: float, new_price: float, change_pct: float) -> str:
    direction = "🔺" if change_pct > 0 else "🔻"
    return (
        f"{direction} ALERTA {asset_symbol}\n"
        f"  Anterior: ${old_price:,.2f}\n"
        f"  Atual:    ${new_price:,.2f}\n"
        f"  Variação: {change_pct:+.2f}%"
    )

def run_price_check(dry_run=False) -> Tuple[List[str], Dict]:
    log("=== PRICE MONITOR ===")
    log(f"Modo: {'DRY-RUN' if dry_run else 'PRODUÇÃO'}")
    
    assets_cfg = load_assets()
    assets = assets_cfg.get("assets", {})
    
    asset_ids = [v["id"] for v in assets.values() if v.get("monitor")]
    thresholds = {v["symbol"]: v["alert_threshold_pct"] for v in assets.values() if v.get("monitor")}
    
    if not asset_ids:
        log("Nenhum asset configurado para monitoramento", "WARN")
        return [], {}
    
    log(f"Assets monitorados: {asset_ids}")
    log(f"Thresholds: {thresholds}")
    
    data = fetch_prices(asset_ids)
    state = get_state("prices")
    alerts = []
    current_prices = {}
    
    for symbol, cfg in assets.items():
        if not cfg.get("monitor"):
            continue
        coin_id = cfg["id"]
        if coin_id not in data:
            log(f"Sem dados para {coin_id} ({cfg['symbol']})", "WARN")
            continue
        
        price_usd = data[coin_id]["usd"]
        change_24h = data[coin_id].get("usd_24h_change", 0)
        current_prices[coin_id] = price_usd
        
        prev = state.get(coin_id)
        cfg_symbol = cfg["symbol"].upper()
        threshold = thresholds.get(cfg_symbol, 5.0)
        
        if prev is not None:
            diff_pct = ((price_usd - prev) / prev) * 100
            log(f"{cfg['symbol']}: ${price_usd:,.2f} (anterior: ${prev:,.2f}, diff: {diff_pct:+.2f}%, threshold: {threshold}%)")
            if abs(diff_pct) >= threshold:
                alerts.append(format_alert(cfg["symbol"], prev, price_usd, diff_pct))
                log(f"ALERTA: {cfg['symbol']} variou {diff_pct:+.2f}% (threshold: {threshold}%)", "WARN")
        else:
            log(f"{cfg['symbol']}: ${price_usd:,.2f} (24h: {change_24h:+.2f}%) — primeiro registo")
    
    if not dry_run:
        state.update(current_prices)
        log(f"Estado salvo: {len(current_prices)} preços")
    else:
        log("[DRY-RUN] Estado NÃO salvo", "WARN")
    
    log("")
    log("=== RESUMO PRICE MONITOR ===")
    if alerts:
        log(f"Alertas detetados: {len(alerts)}", "WARN")
    else:
        log("Sem alertas. Preços estáveis.")
    
    return alerts, current_prices

def main():
    parser = argparse.ArgumentParser(description="Price Monitor")
    parser.add_argument("--dry-run", action="store_true", help="Simula execução")
    args = parser.parse_args()
    
    alerts, _ = run_price_check(dry_run=args.dry_run)
    sys.exit(3 if alerts else 0)

if __name__ == "__main__":
    main()
