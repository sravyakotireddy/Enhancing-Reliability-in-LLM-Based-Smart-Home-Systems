import os
import json
import csv
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def default_rule_response(parsed_command):
    now = datetime.now()
    return {
        "rule_id": "rule_" + now.strftime("%Y%m%d%H%M%S"),
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "rule_type": parsed_command.get("type", "unknown"),
        "trigger": "immediate",
        "conditions": [],
        "actions": parsed_command.get("actions", []),
        "status": "generated"
    }


def generate_rule_with_llm(parsed_command):
    prompt = f"""
You are a smart home rule generator.

Convert the parsed smart-home command into a clean rule JSON.

Parsed command:
{json.dumps(parsed_command, indent=2)}

Rules:
- Return only JSON.
- Do not execute anything.
- Keep snake_case.
- For simple commands, trigger should be "immediate".
- For conditional commands, convert condition into "conditions" list.
- For scheduled commands, convert schedule into "trigger".
- Keep all actions in "actions" list.
- Do not add devices, rooms, or actions that are not in the parsed command.

JSON format:
{{
  "rule_type": "",
  "trigger": "",
  "conditions": [],
  "actions": [
    {{
      "room": "",
      "device": "",
      "action": "",
      "value": "",
      "condition": null
    }}
  ],
  "status": " generated"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )

        result = response.choices[0].message.content
        print("RAW RULE OUTPUT:", result)

        rule = json.loads(result)

        rule["rule_id"] = "rule_" + datetime.now().strftime("%Y%m%d%H%M%S")
        rule["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return rule

    except Exception as e:
        print("Rule generation error:", e)
        return default_rule_response(parsed_command)


def save_rule_log(rule):
    os.makedirs("logs", exist_ok=True)

    file_path = "logs/rule_logs.csv"
    file_exists = os.path.isfile(file_path)

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "rule_id",
                "rule_type",
                "trigger",
                "rule_json"
            ])

        writer.writerow([
            rule.get("timestamp"),
            rule.get("rule_id"),
            rule.get("rule_type"),
            rule.get("trigger"),
            json.dumps(rule)
        ])


def run_module2(parsed_command):
    rule = generate_rule_with_llm(parsed_command)
    save_rule_log(rule)
    return rule