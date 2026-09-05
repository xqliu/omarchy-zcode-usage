#!/usr/bin/python3
# omarchy:summary=Print the ZCode usage record as JSON
"""Collect ZCode usage into one display-ready JSON record.

Local stats come from ZCode's own SQLite usage database at
~/.zcode/cli/db/db.sqlite: turn_usage holds one row per agent turn and
model_usage one row per model request, both with token counts. The agents
panel only ever reads the JSON this prints.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

AGENT_ID = "zcode"
AGENT_NAME = "ZCode"

HOME = Path.home()
DB_PATH = HOME / ".zcode" / "cli" / "db" / "db.sqlite"
PLAN_CACHE = HOME / ".zcode" / "v2" / "coding-plan-cache.json"


def local_day(value):
  try:
    ms = int(value or 0)
  except Exception:
    ms = 0
  if ms <= 0:
    return datetime.now().strftime("%Y-%m-%d")
  if ms < 10_000_000_000:
    ms *= 1000
  return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def number(value):
  try:
    return int(value or 0)
  except Exception:
    return 0


def empty_bucket():
  return {
    "inputTokens": 0,
    "outputTokens": 0,
    "cacheReadInputTokens": 0,
    "cacheCreationInputTokens": 0,
  }


def tier_label():
  # coding-plan-cache.json lists the plan entitlements the CLI knows about;
  # the available one is the plan this usage ran on.
  try:
    data = json.loads(PLAN_CACHE.read_text())
    items = (data.get("entryStatus") or {}).get("items") or {}
    for key in sorted(items):
      entry = items[key] or {}
      if entry.get("status") == "available" and "plan" in key:
        return key.split(":", 1)[1].replace("-", " ").title()
  except Exception:
    pass
  return ""


def main():
  now = datetime.now()
  today = now.strftime("%Y-%m-%d")
  recent_dates = [(now - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
  recent = {day: {"date": day, "messageCount": 0} for day in recent_dates}
  today_tokens_by_model = {}
  model_usage = {}
  today_sessions = set()
  active_days = set()

  today_prompts = 0
  today_total_tokens = 0
  total_prompts = 0
  total_sessions = set()

  record = {
    "schemaVersion": 1,
    "id": AGENT_ID,
    "name": AGENT_NAME,
    "updatedAt": datetime.now(timezone.utc).isoformat(),
    "ready": DB_PATH.exists(),
    "hasLocalStats": True,
    "hasPromptStats": True,
  }

  tier = tier_label()
  if tier:
    record["tierLabel"] = tier

  if not DB_PATH.exists():
    record["usageStatusText"] = "ZCode unavailable"
    record["authHelpText"] = "No usage database at " + str(DB_PATH)
    print(json.dumps(record, separators=(",", ":")))
    return

  connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
  try:
    turns = connection.execute(
      "SELECT session_id, started_at, computed_total_tokens FROM turn_usage"
    ).fetchall()
    models = connection.execute(
      "SELECT model_id, started_at, input_tokens, output_tokens,"
      " cache_creation_input_tokens, cache_read_input_tokens, computed_total_tokens, status"
      " FROM model_usage"
    ).fetchall()
  finally:
    connection.close()

  for session_id, started_at, total in turns:
    day = local_day(started_at)
    total_prompts += 1
    total_sessions.add(session_id)
    active_days.add(day)
    # The panel renders recentDays.messageCount as a token total, despite the
    # field name — the stock claude/codex collectors fill it the same way.
    if day in recent:
      recent[day]["messageCount"] += number(total)
    if day == today:
      today_prompts += 1
      today_total_tokens += number(total)
      today_sessions.add(session_id)

  for model_id, started_at, input_t, output_t, cache_write, cache_read, total, status in models:
    if str(status or "") == "running":
      continue
    day = local_day(started_at)
    model = str(model_id or "unknown")
    bucket = model_usage.setdefault(model, empty_bucket())
    bucket["inputTokens"] += number(input_t)
    bucket["outputTokens"] += number(output_t)
    bucket["cacheReadInputTokens"] += number(cache_read)
    bucket["cacheCreationInputTokens"] += number(cache_write)
    if day == today:
      today_tokens_by_model[model] = today_tokens_by_model.get(model, 0) + number(total)

  record.update({
    "todayPrompts": today_prompts,
    "todaySessions": len(today_sessions),
    "todayTotalTokens": today_total_tokens,
    "todayTokensByModel": today_tokens_by_model,
    "recentDays": [recent[day] for day in recent_dates],
    "totalPrompts": total_prompts,
    "totalSessions": len(total_sessions),
    "activeDays": len(active_days),
    "modelUsage": model_usage,
  })
  print(json.dumps(record, separators=(",", ":")))


if __name__ == "__main__":
  main()
