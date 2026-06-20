import os
import json
import csv
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from module_personalization import apply_personalization, save_user_preference

load_dotenv()  # loads .env file

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def parse_with_llm(command):
    prompt = f"""
You are a smart home command parser.

Parse ANY smart-home command into valid JSON.

Rules:
- Return only JSON.
- Always include "type", "phrase", "condition", "schedule", and "actions".
- If command has multiple actions, put them in "actions" list.
- If command affects all rooms, use "room": "all".
- Do not use "room": "all" unless the user explicitly says all, every, whole house, or everywhere.
- If user does not mention a room, use "room": "unknown".
- If command is not smart-home related, use "type": "unknown".
- If user is teaching a personal preference, use "type": "preference".
- For preference commands, extract the trigger phrase separately in "phrase".
- Preference examples:
  - "When I say movie mode, turn off lights and turn on TV"
  - "When I say make it cool, set bedroom AC to 20"
- Use snake_case for phrase, room, device, and action.
- Common actions: turn_on, turn_off, open, close, lock, unlock, set_temperature, set_volume, set_channel, read.
- Common rooms: living_room, bedroom_1, bedroom_2, kitchen, washroom, garage.
- If command has multiple actions, return a list in "actions"
- Each action can have its own condition
- If condition applies to only one action, attach it inside that action
- If condition applies to entire command, use top-level "condition"
- Use "bulk" only for all/every commands.
- Use "multi_action" when multiple specific actions are requested.
- Always include "condition": null inside each action unless that specific action has a condition.
- Use lowercase snake_case only, e.g. ac, tv, turn_on.
- Map "temp", "house temp", "home temp", "room temp", and "temperature" to sensor: "temperature".
- Map "main door", "front door", and "entrance door" to device "door".
- For doors, "turn on" means "open".
- For doors, "turn off" means "close".
- If user says "main door" or "front door" and no room is given, use "living_room" as the default location.

Command:
"{command}"

JSON format:
{{
  "type": "simple | conditional | scheduled | query | bulk | preference | multi_action | unknown",
  "phrase": "",
  "condition": null,
  "schedule": null,
  "actions": [
    {{
      "room": "",
      "device": "",
      "action": "",
      "value": "",
      "condition": null
    }}
  ]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"}
    )

    result = response.choices[0].message.content
    print("RAW LLM OUTPUT:", result)

    return json.loads(result)


def save_log(command, parsed):
    os.makedirs("logs", exist_ok=True)

    file_path = "logs/command_logs.csv"
    file_exists = os.path.isfile(file_path)

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow(["timestamp", "command", "parsed_output"])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            command,
            json.dumps(parsed)
        ])


def run_module1(user_id, command=None):
    if command is None:
        command = user_id
        user_id = "default"

    parsed = parse_with_llm(command)

    if "phrase" not in parsed:
        parsed["phrase"] = ""
    if "condition" not in parsed:
        parsed["condition"] = None
    if "schedule" not in parsed:
        parsed["schedule"] = None
    if "actions" not in parsed:
        parsed["actions"] = []

    if parsed.get("type") == "preference":
        save_user_preference(user_id, command, parsed)
    else:
        parsed = apply_personalization(user_id, command, parsed)

    save_log(command, parsed)
    return parsed