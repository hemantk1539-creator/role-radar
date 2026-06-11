"""
config.py - configuration and dedup-history persistence.

Pure I/O layer: loads the YAML strategy config and reads/writes job_history.json.
No business logic lives here. HISTORY_FILE is a module-level constant so tests can
repoint it (config.HISTORY_FILE = ...) without touching the filesystem under the bot.
"""
import yaml
import json
import os

CONFIG_FILE = "job_alert_config.yaml"
HISTORY_FILE = "job_history.json"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            print(f"[WARN] History file corrupt or unreadable: {e}")
            return []
    return []


def save_history(history, config):
    max_h = config["search"].get("max_history", 2000)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-max_h:], f, indent=4)
