import json
import os
import re
from copy import deepcopy
from datetime import datetime


PREFERENCES_FILE = "logs/user_preferences.json"


def normalize_phrase(command):
    phrase = command.strip().lower()
    phrase = re.sub(r"[^a-z0-9]+", "_", phrase)
    return phrase.strip("_")


def load_preferences():
    if not os.path.isfile(PREFERENCES_FILE):
        return []

    try:
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return []


def save_preferences(preferences):
    os.makedirs(os.path.dirname(PREFERENCES_FILE), exist_ok=True)

    with open(PREFERENCES_FILE, "w", encoding="utf-8") as file:
        json.dump(preferences, file, indent=2)


def save_user_preference(user_id, command, parsed_command):
    preferences = load_preferences()
    phrase = normalize_phrase(parsed_command.get("phrase") or command)
    actions = parsed_command.get("actions", [])

    preference = {
        "user_id": user_id,
        "phrase": phrase,
        "actions": actions,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    preferences = [
        item for item in preferences
        if not (
            item.get("user_id") == user_id
            and normalize_phrase(item.get("phrase", "")) == phrase
        )
    ]
    preferences.append(preference)
    save_preferences(preferences)

    return preference


def find_matching_preference(user_id, command):
    phrase = normalize_phrase(command)

    for preference in load_preferences():
        saved_phrase = normalize_phrase(preference.get("phrase", ""))

        if preference.get("user_id") == user_id and saved_phrase == phrase:
            return preference

    return None


def apply_personalization(user_id, command, parsed_command):
    preference = find_matching_preference(user_id, command)

    if not preference:
        return parsed_command

    personalized_command = deepcopy(parsed_command)
    personalized_command["type"] = "personalized"
    personalized_command["phrase"] = preference.get("phrase")
    personalized_command["actions"] = preference.get("actions", [])

    return personalized_command
