#!/usr/bin/env python3
"""
CLI Entrypoint — Wrapper unificado para o yield-scanner.

Uso:
  python scanner_cli.py scan        # Executa defillama_scanner
  python scanner_cli.py apr         # Executa apr_scanner
  python scanner_cli.py prices      # Executa price_monitor
  python scanner_cli.py report      # Executa daily_report
  python scanner_cli.py full        # Executa scan + apr + prices

Flags:
  --json      Output estruturado em JSON
  --dry-run   Simula execução sem gravar no DB/enviar notificações
  --verbose   Verbosity máxima

Exit codes:
  0 = Sucesso
  1 = Erro recuperável (retry permitido)
  2 = Erro fatal (não retry)
  3 = Alertas/Anomalias detetadas (sucesso, mas atenção necessária)
"""

import sys
import json
import time
import traceback
import argparse
from datetime import datetime, timezone
from typing import Any

# Adiciona src/ ao path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "src"))

from src.config import get_db_path, DATA_DIR

def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def run_command(cmd: str, args: argparse.Namespace) -> dict[str, Any]:
    """Executa um comando e retorna resultado estruturado."""
    result = {
        "command": cmd,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "success": False,
        "exit_code": 1,
        "alerts": [],
        "errors": [],
        "metrics": {},
        "duration_seconds": 0,
    }

    start = time.time()

    try:
        if cmd == "scan":
            from defillama_scanner import DefiLlamaScanner, CONFIG
            if args.dry_run:
                log("[DRY-RUN] Modo simulação ativado — não gravar no DB", "WARN")
            scanner = DefiLlamaScanner(CONFIG, dry_run=args.dry_run)
            success = scanner.run()
            result["success"] = success
            result["exit_code"] = 0 if success else 1
            result["metrics"] = scanner.get_metrics()

        elif cmd == "apr":
            from apr_scanner import run_apr_scan
            alerts = run_apr_scan(dry_run=args.dry_run)
            result["alerts"] = alerts
            result["success"] = True
            result["exit_code"] = 3 if alerts else 0

        elif cmd == "prices":
            from price_monitor import run_price_check
            alerts, state = run_price_check(dry_run=args.dry_run)
            result["alerts"] = alerts
            result["success"] = True
            result["exit_code"] = 3 if alerts else 0
            result["metrics"]["prices_checked"] = len(state)

        elif cmd == "report":
            from daily_report import build_daily_report
            report_lines = build_daily_report()
            result["success"] = True
            result["exit_code"] = 0
            result["metrics"]["report_lines"] = len(report_lines)

        elif cmd == "full":
            log("Executando pipeline completo: scan → apr → prices")
            # Scan
            from defillama_scanner import DefiLlamaScanner, CONFIG
            scanner = DefiLlamaScanner(CONFIG, dry_run=args.dry_run)
            scan_ok = scanner.run()
            result["metrics"]["scan"] = scanner.get_metrics()

            # APR
            from apr_scanner import run_apr_scan
            apr_alerts = run_apr_scan(dry_run=args.dry_run)
            result["alerts"].extend(apr_alerts)

            # Prices
            from price_monitor import run_price_check
            price_alerts, _ = run_price_check(dry_run=args.dry_run)
            result["alerts"].extend(price_alerts)

            result["success"] = scan_ok
            result["exit_code"] = 3 if (apr_alerts or price_alerts) else (0 if scan_ok else 1)

        else:
            result["errors"].append(f"Comando desconhecido: {cmd}")
            result["exit_code"] = 2

    except Exception as e:
        result["errors"].append(str(e))
        result["errors"].append(traceback.format_exc())
        result["success"] = False
        result["exit_code"] = 2
        log(f"Erro fatal: {e}", "ERROR")

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description="Yield Scanner CLI")
    parser.add_argument("command", choices=["scan", "apr", "prices", "report", "full"],
                        help="Comando a executar")
    parser.add_argument("--json", action="store_true", help="Output em JSON")
    parser.add_argument("--dry-run", action="store_true", help="Simula execução")
    parser.add_argument("--verbose", action="store_true", default=True,
                        help="Verbosity máxima")
    args = parser.parse_args()

    log(f"=== YIELD SCANNER CLI ===")
    log(f"Comando: {args.command}")
    log(f"Modo: {'DRY-RUN' if args.dry_run else 'PRODUÇÃO'}")
    log(f"DB: {get_db_path()}")
    log(f"Data dir: {DATA_DIR}")
    log(f"")

    result = run_command(args.command, args)

    log(f"")
    log(f"=== RESULTADO ===")
    log(f"Sucesso: {result['success']}")
    log(f"Exit code: {result['exit_code']}")
    log(f"Duração: {result['duration_seconds']}s")
    log(f"Alertas: {len(result['alerts'])}")
    log(f"Erros: {len(result['errors'])}")

    if result["errors"]:
        for err in result["errors"]:
            log(f"Erro: {err}", "ERROR")

    if result["alerts"]:
        log(f"ALERTAS DETETADOS ({len(result['alerts'])})", "WARN")
        for alert in result["alerts"]:
            log(f"  → {alert}", "WARN")

    if args.json:
        print("\n--- JSON OUTPUT ---")
        print(json.dumps(result, indent=2, default=str))

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
