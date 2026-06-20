import csv
import json
import os
from datetime import datetime


def execute_action(action):
    room = action.get("room")
    device = action.get("device")
    act = action.get("action")
    value = action.get("value")

    if value not in ["", None]:
        result = f"Executed: {act} {device} in {room} with value {value}"
    else:
        result = f"Executed: {act} {device} in {room}"

    print(result)
    return result


def save_execution_log(rule, execution_results):
    os.makedirs("logs", exist_ok=True)

    file_path = "logs/execution_logs.csv"
    file_exists = os.path.isfile(file_path)

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "rule_id",
                "rule_type",
                "execution_results",
                "rule_json"
            ])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            rule.get("rule_id"),
            rule.get("rule_type"),
            json.dumps(execution_results),
            json.dumps(rule)
        ])


def run_execution(rule):
    print("\nExecuting rule...\n")

    results = []

    for action in rule.get("actions", []):
        result = execute_action(action)
        results.append(result)

    save_execution_log(rule, results)

    print("\nExecution completed and saved to logs/execution_logs.csv")
    return results