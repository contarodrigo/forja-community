#!/usr/bin/env python3
"""
DefiLlama Yield Scanner
Busca APR/APY de pools DeFiLlama para ETH, SOL, BTC.
Salva em SQLite local.

Uso standalone:
  python defillama_scanner.py
  python defillama_scanner.py --dry-run

Uso via entrypoint:
  python scanner_cli.py scan

Exit codes:
  0 = Sucesso
  1 = Erro na API / falha ao buscar dados
"""

import requests
import sqlite3
import json
import time
import sys
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Optional

from src.config import get_db_path, ensure_data_dir

CONFIG = {
    "api_base": "https://yields.llama.fi",
    "target_chains": ["Base", "Arbitrum", "Polygon", "Hyperliquid L1"],
    "core_assets": ["ETH", "WETH", "SOL", "WSOL", "WBTC", "WBTC.B", "CBBTC", "TBTC", "LBTC", "UBTC", "HBBTC", "BTC.B", "EBTC"],
    "stablecoins": ["USDC", "USDT", "USDC.E", "USDT.E", "DAI", "FRAX", "LUSD", "MIM", "USDZ", "USD₮0"],
    "min_tvl_usd": 100000,
    "min_apy": 10,
    "min_stable_apy": 5,
    "timeout": 60,
    "retries": 3,
}

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{level}] {msg}", flush=True)

class DefiLlamaScanner:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.db_path = str(get_db_path())
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "DefiLlama-Yield-Scanner/1.0 (Educational)",
            "Accept": "application/json",
        })
        self._metrics = {
            "total_pools_api": 0,
            "core_pools_found": 0,
            "stable_pools_found": 0,
            "pools_saved": 0,
            "alerts_triggered": 0,
            "api_retries": 0,
            "api_errors": 0,
            "duration_seconds": 0,
        }
        if self.dry_run:
            log("[DRY-RUN] Banco de dados nao sera inicializado nem alterado", "WARN")
        else:
            self._init_db()

    def _init_db(self):
        ensure_data_dir()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pools (
                pool_id TEXT PRIMARY KEY, pool_type TEXT DEFAULT 'core',
                chain TEXT, project TEXT, symbol TEXT,
                tvl_usd REAL, apy REAL, apy_base REAL, apy_reward REAL,
                apy_mean_30d REAL, stablecoin INTEGER, il_risk TEXT,
                exposure TEXT, predictions TEXT, pool_meta TEXT,
                mu REAL, sigma REAL, count INTEGER, outlier INTEGER,
                underlying_tokens TEXT, reward_tokens TEXT,
                url TEXT,
                first_seen TIMESTAMP, last_updated TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apr_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                apy REAL, apy_base REAL, apy_reward REAL, tvl_usd REAL,
                FOREIGN KEY (pool_id) REFERENCES pools(pool_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id TEXT, alert_type TEXT,
                old_value REAL, new_value REAL, change_percent REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pools_chain ON pools(chain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pools_project ON pools(project)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pools_symbol ON pools(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pools_apy ON pools(apy)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_pool_time ON apr_history(pool_id, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_notified ON alerts(notified)")
        try:
            cursor.execute("ALTER TABLE pools ADD COLUMN pool_type TEXT DEFAULT 'core'")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pools_pool_type ON pools(pool_type)")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE pools ADD COLUMN url TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
        log(f"Banco de dados pronto: {self.db_path}")

    def _api_request(self, endpoint, retries=None):
        if retries is None:
            retries = self.config["retries"]
        url = f"{self.config['api_base']}{endpoint}"
        for attempt in range(retries):
            try:
                log(f"API request: {url} (tentativa {attempt + 1}/{retries})")
                response = self.session.get(url, timeout=self.config["timeout"])
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout:
                log(f"Timeout na tentativa {attempt + 1}", "WARN")
                self._metrics["api_retries"] += 1
                time.sleep(2 ** attempt)
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    log("Rate limit (429), aguardando 60s...", "WARN")
                    self._metrics["api_retries"] += 1
                    time.sleep(60)
                else:
                    log(f"HTTP Error {response.status_code}: {e}", "ERROR")
                    self._metrics["api_errors"] += 1
                    return None
            except Exception as e:
                log(f"Erro na request: {e}", "ERROR")
                self._metrics["api_errors"] += 1
                time.sleep(2 ** attempt)
        log(f"Falha após {retries} tentativas", "ERROR")
        return None

    def fetch_all_pools(self):
        data = self._api_request("/pools")
        if data and "data" in data:
            pools = data["data"]
            self._metrics["total_pools_api"] = len(pools)
            log(f"Total de pools recebidas da API: {len(pools)}")
            return pools
        log("Resposta da API inválida ou sem campo 'data'", "ERROR")
        return []

    def filter_pools(self, pools):
        core_pools = []
        stablecoin_pools = []
        core_set = set(self.config["core_assets"])
        stable_set = set(self.config["stablecoins"])
        log(f"Filtros: chains={self.config['target_chains']} | min_tvl=${self.config['min_tvl_usd']:,}")
        log(f"Core assets: {len(core_set)} | Stablecoins: {len(stable_set)}")
        skipped_chain = 0
        skipped_tvl = 0
        skipped_format = 0
        for pool in pools:
            chain = pool.get("chain", "")
            if chain not in self.config["target_chains"]:
                skipped_chain += 1
                continue
            symbol = pool.get("symbol", "").upper()
            parts = [p.strip() for p in symbol.replace("-", "/").split("/")]
            if len(parts) != 2:
                skipped_format += 1
                continue
            a, b = parts[0], parts[1]
            tvl = pool.get("tvlUsd", 0) or 0
            if tvl < self.config["min_tvl_usd"]:
                skipped_tvl += 1
                continue
            apy = pool.get("apy", 0) or 0
            if a in core_set or b in core_set:
                if apy >= self.config["min_apy"]:
                    core_pools.append(pool)
            elif a in stable_set and b in stable_set:
                if apy >= self.config.get("min_stable_apy", 5):
                    stablecoin_pools.append(pool)
        core_pools.sort(key=lambda x: x.get("apy", 0) or 0, reverse=True)
        stablecoin_pools.sort(key=lambda x: x.get("apy", 0) or 0, reverse=True)
        self._metrics["core_pools_found"] = len(core_pools)
        self._metrics["stable_pools_found"] = len(stablecoin_pools)
        log(f"Pools filtradas: {len(core_pools)} core, {len(stablecoin_pools)} stablecoin")
        log(f"Skipados: {skipped_chain} chain, {skipped_tvl} TVL, {skipped_format} formato")
        return core_pools, stablecoin_pools

    def save_pools(self, pools, pool_type="core"):
        if self.dry_run:
            log(f"[DRY-RUN] Não gravando {len(pools)} pools tipo={pool_type}", "WARN")
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        alerts_triggered = []
        for pool in pools:
            pool_id = pool.get("pool")
            if not pool_id:
                continue
            cursor.execute("SELECT apy, tvl_usd FROM pools WHERE pool_id = ?", (pool_id,))
            old = cursor.fetchone()
            pool_url = f"https://defillama.com/yields/pool/{pool_id}"
            cursor.execute("""
                INSERT OR REPLACE INTO pools (
                    pool_id, pool_type, chain, project, symbol, tvl_usd, apy, apy_base, apy_reward,
                    apy_mean_30d, stablecoin, il_risk, exposure, predictions, pool_meta,
                    mu, sigma, count, outlier, underlying_tokens, reward_tokens, url,
                    first_seen, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT first_seen FROM pools WHERE pool_id = ?), ?), ?)
            """, (
                pool_id, pool_type, pool.get("chain", ""), pool.get("project", ""), pool.get("symbol", ""),
                pool.get("tvlUsd", 0), pool.get("apy", 0), pool.get("apyBase", 0), pool.get("apyReward", 0),
                pool.get("apyMean30d", 0),
                1 if pool.get("stablecoin", False) else 0,
                pool.get("ilRisk", ""), pool.get("exposure", ""),
                json.dumps(pool.get("predictions", {})) if pool.get("predictions") else None,
                pool.get("poolMeta", ""),
                pool.get("mu", 0), pool.get("sigma", 0), pool.get("count", 0),
                1 if pool.get("outlier", False) else 0,
                json.dumps(pool.get("underlyingTokens", [])) if pool.get("underlyingTokens") else None,
                json.dumps(pool.get("rewardTokens", [])) if pool.get("rewardTokens") else None,
                pool_url,
                pool_id, now, now
            ))
            cursor.execute("""
                INSERT INTO apr_history (pool_id, apy, apy_base, apy_reward, tvl_usd)
                VALUES (?, ?, ?, ?, ?)
            """, (pool_id, pool.get("apy", 0), pool.get("apyBase", 0), pool.get("apyReward", 0), pool.get("tvlUsd", 0)))
            if old:
                old_apy, old_tvl = old
                new_apy = pool.get("apy", 0) or 0
                if old_apy and old_apy != 0:
                    change_pct = ((new_apy - old_apy) / abs(old_apy)) * 100
                    if abs(change_pct) > 50:
                        alerts_triggered.append({
                            "pool_id": pool_id,
                            "symbol": pool.get("symbol", "?"),
                            "type": "apy_change",
                            "old": old_apy,
                            "new": new_apy,
                            "change": change_pct
                        })
                        cursor.execute("""
                            INSERT INTO alerts (pool_id, alert_type, old_value, new_value, change_percent)
                            VALUES (?, ?, ?, ?, ?)
                        """, (pool_id, "apy_change", old_apy, new_apy, change_pct))
        conn.commit()
        conn.close()
        self._metrics["pools_saved"] += len(pools)
        self._metrics["alerts_triggered"] += len(alerts_triggered)
        if alerts_triggered:
            log(f"Alertas de variação APY >50%: {len(alerts_triggered)}", "WARN")
            for alert in alerts_triggered[:5]:
                log(f"   → {alert['symbol']} ({alert['pool_id']}): {alert['change']:+.1f}%", "WARN")
        log(f"Pools salvas: {len(pools)} (tipo={pool_type})")

    def get_top_opportunities(self, chain=None, min_tvl=None, limit=20, pool_type=None):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = "SELECT * FROM pools WHERE 1=1"
        params = []
        if chain:
            query += " AND chain = ?"
            params.append(chain)
        if min_tvl:
            query += " AND tvl_usd >= ?"
            params.append(min_tvl)
        if pool_type:
            query += " AND pool_type = ?"
            params.append(pool_type)
        query += " ORDER BY apy DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_metrics(self):
        return dict(self._metrics)

    def print_top(self, pools, title):
        log("")
        log(f"🏆 {title} ({len(pools)} encontradas)")
        log("-" * 100)
        for i, pool in enumerate(pools[:10], 1):
            chain = str(pool.get("chain", "") or "")
            project = str(pool.get("project", "") or "")
            symbol = str(pool.get("symbol", "") or "")
            apy = pool.get("apy") or 0
            tvl = pool.get("tvl_usd") or pool.get("tvlUsd") or 0
            apy_base = pool.get("apy_base") or pool.get("apyBase") or 0
            apy_reward = pool.get("apy_reward") or pool.get("apyReward") or 0
            pool_url = pool.get("url", "")
            if not pool_url and pool.get("pool"):
                pool_url = f"https://defillama.com/yields/pool/{pool['pool']}"
            if pool_url:
                log(f"{i:2d}. [{chain:<12}] {project:<22} | {symbol:<22} | APY: {apy:>8.2f}% | TVL: ${tvl:>12,.0f} | Base: {apy_base:>6.2f}% | Reward: {apy_reward:>6.2f}% | {pool_url}")
            else:
                log(f"{i:2d}. [{chain:<12}] {project:<22} | {symbol:<22} | APY: {apy:>8.2f}% | TVL: ${tvl:>12,.0f} | Base: {apy_base:>6.2f}% | Reward: {apy_reward:>6.2f}%")

    def run(self):
        log("=== DEFILLAMA YIELD SCANNER ===")
        log(f"Modo: {'DRY-RUN' if self.dry_run else 'PRODUÇÃO'}")
        start_time = time.time()
        pools = self.fetch_all_pools()
        if not pools:
            log("Falha ao buscar pools da API — abortando", "ERROR")
            self._metrics["duration_seconds"] = round(time.time() - start_time, 2)
            return False
        core_pools, stablecoin_pools = self.filter_pools(pools)
        self.save_pools(core_pools, pool_type="core")
        self.save_pools(stablecoin_pools, pool_type="stablecoin")
        top_core = core_pools[:10] if self.dry_run else self.get_top_opportunities(limit=10, pool_type="core")
        self.print_top(top_core, "TOP 10 OPORTUNIDADES CORE (ETH/SOL/BTC)")
        top_stable = stablecoin_pools[:10] if self.dry_run else self.get_top_opportunities(limit=10, pool_type="stablecoin")
        self.print_top(top_stable, "TOP 10 STABLECOINS")
        elapsed = time.time() - start_time
        self._metrics["duration_seconds"] = round(elapsed, 2)
        total_pools = len(core_pools) + len(stablecoin_pools)
        log("")
        log("=== RESUMO ===")
        log(f"Scan completo em {elapsed:.1f}s")
        log(f"Total pools API: {self._metrics['total_pools_api']}")
        log(f"Core filtradas: {len(core_pools)}")
        log(f"Stablecoins: {len(stablecoin_pools)}")
        log(f"Total relevantes: {total_pools}")
        log(f"Alertas variação: {self._metrics['alerts_triggered']}")
        log(f"API retries: {self._metrics['api_retries']}")
        log(f"API errors: {self._metrics['api_errors']}")
        return True

def main():
    parser = argparse.ArgumentParser(description="DefiLlama Yield Scanner")
    parser.add_argument("--dry-run", action="store_true", help="Simula execução sem gravar no DB")
    args = parser.parse_args()
    scanner = DefiLlamaScanner(CONFIG, dry_run=args.dry_run)
    success = scanner.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
