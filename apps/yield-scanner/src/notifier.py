"""Módulo de notificação — Telegram opcional, com fallback para stdout."""

import os
import requests
from typing import Optional
from src.config import load_telegram_config


class Notifier:
    """Envia notificações via Telegram se configurado, senão loga em stdout."""

    def __init__(self, force_disable: bool = False):
        cfg = load_telegram_config()
        self.enabled = cfg.get("telegram", {}).get("enabled", True) and not force_disable
        self.bot_token = os.environ.get(cfg["telegram"]["bot_token_env"]) if self.enabled else None
        self.chat_id = os.environ.get(cfg["telegram"]["chat_id_env"]) if self.enabled else None
        self._available = self.enabled and bool(self.bot_token) and bool(self.chat_id)

    def is_available(self) -> bool:
        return self._available

    def send(self, message: str, parse_mode: str = "HTML") -> dict:
        """Envia mensagem e retorna um dict com status."""
        result = {
            "sent": False,
            "channel": "telegram" if self._available else "stdout",
            "error": None,
        }

        if self._available:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                }
                r = requests.post(url, json=payload, timeout=15)
                r.raise_for_status()
                result["sent"] = True
                result["message_id"] = r.json().get("result", {}).get("message_id")
                print(f"[Notifier] Telegram OK (msg_id={result['message_id']})")
            except Exception as e:
                result["error"] = str(e)
                print(f"[Notifier] Erro Telegram: {e}. Fallback para stdout.")
                print(f"[Notifier][FALLBACK] {message[:500]}")
        else:
            print(f"[Notifier] Telegram não configurado. Mensagem:")
            print(f"[Notifier][STDOUT] {message[:500]}")
            result["sent"] = True  # Considerado "entregue" via stdout

        return result

    def send_alert(self, title: str, body: str) -> dict:
        """Formata e envia alerta estruturado."""
        message = f"🚨 <b>{title}</b>\n\n{body}"
        return self.send(message)

    def send_report(self, title: str, lines: list[str]) -> dict:
        """Formata e envia relatório estruturado."""
        body = "\n".join(lines)
        message = f"📊 <b>{title}</b>\n\n{body}"
        return self.send(message)
