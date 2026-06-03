#!/usr/bin/env python3
"""
APR Scanner
Analisa anomalias de APR nos pools do DB local (salvos pelo defillama_scanner).
Não busca mais na API por pool_id — usa o SQLite local com histórico.

Uso:
  python apr_scanner.py
  python apr_scanner.py --dry-run

Exit codes:
  0 = Sem anomalias
  3 = Anomalias detetadas
"""

import sqlite3
import sys
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Optional

from src.config import get_db_path

# Thresholds ajustados para reduzir ruído
APR_MIN_THRESHOLD_CORE = 50.0      # Core assets: só alerta se >50%
APR_MIN_THRESHOLD_STABLE = 15.0    # Stablecoins: alerta se >15%
APR_MAX_THRESHOLD = 200.0          # Crítico
NORMAL_APR_MARGIN = 30.0           # Variação histórica
MIN_TVL_FOR_ALERT = 500_000
MIN_HISTORY_SAMPLES = 3            # Mínimo de amostras para análise histórica

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def get_historical_avg(pool_id: str, days: int = 7) -> Optional[float]:
    conn = sqlite3.connect(str(get_db_path()))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT AVG(apy) FROM apr_history
        WHERE pool_id = ? AND timestamp > datetime('now', ?)
    """, (pool_id, f"-{days} days"))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return float(row[0])
    return None

def get_pool_history_count(pool_id: str) -> int:
    conn = sqlite3.connect(str(get_db_path()))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM apr_history WHERE pool_id = ?", (pool_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def detect_anomalies_from_db() -> List[Dict]:
    db_path = get_db_path()
    if not db_path.exists():
        log(f"Banco ainda nao existe: {db_path}", "WARN")
        log("Execute primeiro: python scanner_cli.py scan", "WARN")
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'pools'")
    if cursor.fetchone() is None:
        conn.close()
        log("Tabela 'pools' ainda nao existe no banco local", "WARN")
        log("Execute primeiro: python scanner_cli.py scan", "WARN")
        return []
    
    cursor.execute("""
        SELECT pool_id, chain, project, symbol, apy, tvl_usd, pool_type, url
        FROM pools
        WHERE tvl_usd >= ?
        ORDER BY tvl_usd DESC
    """, (MIN_TVL_FOR_ALERT,))
    
    pools = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    log(f"Pools elegíveis para análise (TVL >= ${MIN_TVL_FOR_ALERT:,}): {len(pools)}")
    log(f"Thresholds: core>{APR_MIN_THRESHOLD_CORE}%, stable>{APR_MIN_THRESHOLD_STABLE}%, crítico>{APR_MAX_THRESHOLD}%, margin>{NORMAL_APR_MARGIN}%")
    
    alerts = []
    
    for pool in pools:
        pool_id = pool["pool_id"]
        apy = pool["apy"] or 0
        tvl = pool["tvl_usd"] or 0
        pool_type = pool.get("pool_type", "core")
        
        if apy <= 0:
            continue
        
        # Define threshold baseado no tipo
        min_threshold = APR_MIN_THRESHOLD_STABLE if pool_type == "stablecoin" else APR_MIN_THRESHOLD_CORE
        
        hist_avg = get_historical_avg(pool_id, days=7)
        hist_count = get_pool_history_count(pool_id)
        
        alert_parts = []
        alert_level = None
        
        # 🎯 Oportunidade: APR muito alto (>200%)
        if apy > APR_MAX_THRESHOLD:
            alert_level = "🎯 ALERTA DE OPORTUNIDADE"
            alert_parts.append(f"APY {apy:.2f}% > limiar {APR_MAX_THRESHOLD}%")
        
        # 💰 Yield acima da média por tipo
        elif apy > min_threshold:
            alert_level = "💰 YIELD ACIMA DA MÉDIA"
            alert_parts.append(f"APY {apy:.2f}% > limiar {min_threshold}%")
        
        # 🔥 Tendência alta: só se tiver histórico suficiente
        if hist_avg and hist_count >= MIN_HISTORY_SAMPLES:
            margin = ((apy - hist_avg) / abs(hist_avg)) * 100
            if margin > NORMAL_APR_MARGIN:
                alert_parts.append(f"{margin:.1f}% acima da média 7d ({hist_avg:.2f}%)")
                if not alert_level:
                    alert_level = "🔥 TENDÊNCIA ALTA"
        
        if alert_level:
            pool_url = pool.get("url", "")
            alert_text = (
                f"{alert_level} — {pool['symbol']} ({pool['project']}) [{pool['chain']}]\n"
                f"   APY atual: {apy:.2f}%"
            )
            if hist_avg and hist_count >= MIN_HISTORY_SAMPLES:
                alert_text += f" | Média 7d: {hist_avg:.2f}% ({hist_count} amostras)"
            elif hist_count > 0:
                alert_text += f" | Histórico: {hist_count} amostra(s) (insuficiente para análise)"
            alert_text += f" | TVL: ${tvl:,.0f} | Tipo: {pool_type}"
            if pool_url:
                alert_text += f"\n   Link: {pool_url}"
            
            alerts.append({
                "level": alert_level,
                "text": alert_text,
                "pool_id": pool_id,
                "apy": apy,
                "tvl": tvl,
                "chain": pool["chain"],
                "symbol": pool["symbol"],
            })
            log(f"ALERTA: {pool['symbol']} ({pool['chain']}) — APY {apy:.2f}%", "WARN")
    
    return alerts

def run_apr_scan(dry_run=False) -> List[str]:
    log("=== APR SCANNER ===")
    log(f"Modo: {'DRY-RUN' if dry_run else 'PRODUÇÃO'}")
    
    alerts = detect_anomalies_from_db()
    
    log("")
    log("=== RESUMO APR SCANNER ===")
    if alerts:
        log(f"Oportunidades detetadas: {len(alerts)}", "WARN")
        for a in alerts:
            log(f"  → {a['text']}", "WARN")
    else:
        log("Nenhuma oportunidade detetada")
    
    return [a["text"] for a in alerts]

def main():
    parser = argparse.ArgumentParser(description="APR Scanner")
    parser.add_argument("--dry-run", action="store_true", help="Simula execução")
    args = parser.parse_args()
    
    alerts = run_apr_scan(dry_run=args.dry_run)
    sys.exit(3 if alerts else 0)

if __name__ == "__main__":
    main()
