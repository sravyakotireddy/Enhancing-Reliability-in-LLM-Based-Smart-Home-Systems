import copy
import csv
import json
import os
import re
from collections import Counter

from module3_hallucination_checker import (
    ROOMS,
    DEVICE_CATALOG,
    SENSOR_CATALOG,
    check_hallucination,
    normalize_location,
)


USER_PRESENCE = {
    "living_room": True,
    "bedroom_1": False,
    "bedroom_2": False,
    "kitchen": False,
    "washroom": False,
    "garage": False
}

# Colloquial / LLM names → device id in data/devices.csv
DEVICE_ALIASES = {
    "exhaust": "exhaust_fan",
}


def resolve_device_alias(device):
    if not device:
        return device
    return DEVICE_ALIASES.get(device, device)


def find_device_rooms(device):
    rooms = []

    for room in ROOMS:
        if device in DEVICE_CATALOG.get(room, {}):
            rooms.append(room)

    return rooms


def get_related_devices_for_sensor(sensor):
    for row in SENSOR_CATALOG:
        if row.get("sensor") == sensor:
            related = row.get("related_devices", "")
            return [d.strip() for d in related.split(";") if d.strip()]

    return []


def get_device_from_sensor(action):
    room = action.get("room")
    device = action.get("device")
    act = action.get("action")

    related_devices = get_related_devices_for_sensor(device)

    if not related_devices:
        return None, "No related device found for sensor"

    room_devices = DEVICE_CATALOG.get(room, {})

    for related_device in related_devices:
        if related_device in room_devices:
            allowed_actions = room_devices[related_device]

            if act in allowed_actions:
                return related_device, f"Mapped sensor '{device}' to device '{related_device}'"

            if "turn_on" in allowed_actions:
                action["action"] = "turn_on"
                return related_device, f"Mapped sensor '{device}' to device '{related_device}' with action 'turn_on'"

    return None, f"No related device available in room '{room}'"


def get_rooms_with_user_presence(device):
    rooms = []

    for room, present in USER_PRESENCE.items():
        if present and device in DEVICE_CATALOG.get(room, {}):
            rooms.append(room)

    return rooms


def get_most_used_room_from_logs(device, candidate_rooms):
    log_file = "logs/command_logs.csv"

    if not os.path.exists(log_file):
        return None, "No command log found"

    room_counter = Counter()
    latest_room = None

    with open(log_file, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            parsed_text = row.get("parsed_output")

            if not parsed_text:
                continue

            try:
                parsed = json.loads(parsed_text)
            except Exception:
                continue

            for action in parsed.get("actions", []):
                room = action.get("room")
                action_device = action.get("device")

                if action_device == device and room in candidate_rooms:
                    room_counter[room] += 1
                    latest_room = room

    if not room_counter:
        return None, "No past usage found"

    most_common = room_counter.most_common()

    if len(most_common) == 1:
        return most_common[0][0], "Selected room from most-used command history"

    if most_common[0][1] > most_common[1][1]:
        return most_common[0][0], "Selected room from most-used command history"

    if latest_room:
        return latest_room, "Selected room from latest command history"

    return None, "History tied and no latest room found"


def infer_room(device):
    possible_rooms = find_device_rooms(device)

    if len(possible_rooms) == 1:
        return possible_rooms[0], f"Selected '{possible_rooms[0]}' because device exists only there"

    if not possible_rooms:
        return None, f"Device '{device}' not found in catalog"

    present_rooms = get_rooms_with_user_presence(device)

    if len(present_rooms) == 1:
        return present_rooms[0], f"Selected '{present_rooms[0]}' because user is present there"

    if len(present_rooms) > 1:
        room, reason = get_most_used_room_from_logs(device, present_rooms)

        if room:
            return room, reason

        return None, f"User present in multiple rooms {present_rooms}. Need clarification."

    room, reason = get_most_used_room_from_logs(device, possible_rooms)

    if room:
        return room, reason

    if len(possible_rooms) == 2:
        chosen = possible_rooms[0]
        return chosen, (
            f"Selected '{chosen}' because device exists in {possible_rooms} "
            "with no presence or history tie-break; using first room in home order"
        )

    return None, f"Device '{device}' exists in multiple rooms {possible_rooms}. Need clarification."


def mitigate_action(action):
    fixed = copy.deepcopy(action)

    notes = []
    raw_device = fixed.get("device")
    if raw_device:
        resolved = resolve_device_alias(raw_device)
        if resolved != raw_device:
            fixed["device"] = resolved
            notes.append(f"Mapped device '{raw_device}' to '{resolved}'")

    room = fixed.get("room")
    device = fixed.get("device")

    # Case 1: unknown room
    if room in ["unknown", "", None]:
        inferred_room, reason = infer_room(device)

        if inferred_room:
            fixed["room"] = inferred_room
            if notes:
                return fixed, "; ".join(notes + [reason])
            return fixed, reason

        if notes:
            return fixed, "; ".join(notes + [reason])
        return fixed, reason

    # Case 2: LLM used sensor as device, e.g. temperature as device
    related_device, reason = get_device_from_sensor(fixed)

    if related_device:
        fixed["device"] = related_device
        return fixed, reason

    # Case 3: device exists, but in another room
    if room in ROOMS:
        if device not in DEVICE_CATALOG.get(room, {}):
            possible_rooms = find_device_rooms(device)

            if len(possible_rooms) == 1:
                fixed["room"] = possible_rooms[0]
                return fixed, f"Moved device '{device}' to room '{possible_rooms[0]}'"

            if len(possible_rooms) > 1:
                inferred_room, reason = infer_room(device)

                if inferred_room:
                    fixed["room"] = inferred_room
                    return fixed, reason

                return fixed, reason

    return fixed, "No mitigation found"


# Raw string condition → structured fields; sensor names match data/sensors.csv
SENSOR_TOKEN_ALIASES = {
    "temp": "temperature",
    "temperature": "temperature",
    "humidity": "humidity",
    "smoke": "smoke_alarm",
    "smoke_alarm": "smoke_alarm",
    "gas": "gas_sensor",
    "gas_sensor": "gas_sensor",
    "presence": "presence",
    "light": "light_level",
    "light_level": "light_level",
    "brightness": "light_level",
}

def _normalize_condition_operator(op):
    if op is None:
        return op
    op = str(op).strip()
    if op == "=":
        return "=="
    return op


def _parse_condition_numeric_value(text):
    t = str(text).strip().strip('"').strip("'")
    t = re.sub(r"(?i)(°\s*c|°c|\s*c)\s*$", "", t)
    t = re.sub(r"\s*%\s*$", "", t)
    t = t.strip()
    try:
        if "." in t:
            return float(t)
        return int(t)
    except ValueError:
        return t


def _split_raw_condition_string(raw):
    s = (raw or "").strip()
    if not s:
        return None

    m = re.match(
        r"^\s*(?P<sensor>[\w_]+)\s*(?P<op>>=|<=|==|>|<|=)\s*(?P<val>.+)$",
        s,
        re.IGNORECASE,
    )
    if not m:
        return None

    return m.group("sensor"), m.group("op"), m.group("val")


def _canonical_sensor_name(token):
    if not token:
        return None
    key = str(token).strip().lower()
    if not key:
        return None
    return SENSOR_TOKEN_ALIASES.get(key, key)


def _sensor_catalog_bounds(sensor_name):
    for row in SENSOR_CATALOG:
        if row.get("sensor") == sensor_name:
            min_v = row.get("min_value", "")
            max_v = row.get("max_value", "")
            if min_v != "" and max_v != "":
                try:
                    return float(min_v), float(max_v)
                except ValueError:
                    continue
    return None, None


def _user_soft_clamp(sensor_name, value):
    """Apply requested soft bounds before catalog enforcement."""
    if not isinstance(value, (int, float)):
        return value, None

    v = float(value)
    if sensor_name == "temperature":
        lo, hi = -10.0, 50.0
        if v > hi:
            return hi, f"Clamped temperature {value} to {hi}"
        if v < lo:
            return lo, f"Clamped temperature {value} to {lo}"
        return v, None

    if sensor_name == "humidity":
        lo, hi = 0.0, 100.0
        if v > hi:
            return hi, f"Clamped humidity {value} to {hi}"
        if v < lo:
            return lo, f"Clamped humidity {value} to {lo}"
        return v, None

    return v, None


def _clamp_condition_value(sensor_name, value):
    reasons = []

    if isinstance(value, (int, float)):
        v, note = _user_soft_clamp(sensor_name, value)
        if note:
            reasons.append(note)
        value = v

    if not isinstance(value, (int, float)):
        return value, reasons

    cat_min, cat_max = _sensor_catalog_bounds(sensor_name)
    v = float(value)
    if cat_min is not None and cat_max is not None:
        if v < cat_min:
            reasons.append(
                f"Clamped {sensor_name} value {value} to catalog minimum {cat_min}"
            )
            v = cat_min
        elif v > cat_max:
            reasons.append(
                f"Clamped {sensor_name} value {value} to catalog maximum {cat_max}"
            )
            v = cat_max

    if v == int(v):
        v = int(v)

    return v, reasons


def _default_condition_location(rule):
    actions = rule.get("actions") or []
    if not actions:
        return "all"

    room = actions[0].get("room")
    if room in (None, "", "unknown"):
        return "all"

    return room


def mitigate_condition(condition, rule):
    """
    Normalize a single condition dict: raw string → structured fields,
    infer location, clamp unrealistic numeric values.
    Returns (fixed_condition, reason).
    """
    fixed = copy.deepcopy(condition)
    reasons = []

    raw = fixed.get("condition")
    if isinstance(raw, str) and raw.strip():
        parts = _split_raw_condition_string(raw)
        if parts:
            left, op, right = parts
            sensor = _canonical_sensor_name(left)
            if sensor:
                fixed["sensor"] = sensor
            fixed["operator"] = _normalize_condition_operator(op)
            fixed["value"] = _parse_condition_numeric_value(right)
            reasons.append("Converted raw condition string to structured fields")
            fixed.pop("condition", None)
    elif "condition" in fixed:
        fixed.pop("condition", None)

    sensor = fixed.get("sensor") or fixed.get("condition_type")
    if sensor:
        canon = _canonical_sensor_name(sensor)
        if canon and canon != sensor:
            reasons.append(f"Normalized sensor name '{sensor}' → '{canon}'")
        if canon:
            fixed["sensor"] = canon
        elif not fixed.get("sensor"):
            fixed["sensor"] = str(sensor).strip().lower()
        fixed.pop("condition_type", None)

    op = fixed.get("operator")
    norm_op = _normalize_condition_operator(op)
    if norm_op and norm_op != op:
        reasons.append(f"Normalized operator '{op}' → '{norm_op}'")
        fixed["operator"] = norm_op

    loc = fixed.get("location") or fixed.get("room") or fixed.get("scope")
    if not loc:
        loc = _default_condition_location(rule)
        fixed["location"] = normalize_location(loc)
        reasons.append(f"Inferred condition location '{fixed['location']}'")
    else:
        fixed["location"] = normalize_location(loc)

    for k in ("room", "scope"):
        fixed.pop(k, None)

    sensor_name = fixed.get("sensor")
    if sensor_name and "value" in fixed:
        new_val, clamp_notes = _clamp_condition_value(sensor_name, fixed.get("value"))
        if clamp_notes:
            reasons.extend(clamp_notes)
        fixed["value"] = new_val

    reason = "; ".join(reasons) if reasons else "No condition mitigation"
    return fixed, reason


def _mitigate_first_condition(current_rule):
    conditions = current_rule.get("conditions")
    if not conditions:
        return False, ""

    for gi, group in enumerate(conditions):
        if not isinstance(group, dict):
            continue

        if "any" in group:
            lst = group["any"]
            for i, cond in enumerate(lst):
                before = copy.deepcopy(cond)
                fixed, reason = mitigate_condition(cond, current_rule)
                if fixed != before:
                    lst[i] = fixed
                    return True, reason

        elif "all" in group:
            lst = group["all"]
            for i, cond in enumerate(lst):
                before = copy.deepcopy(cond)
                fixed, reason = mitigate_condition(cond, current_rule)
                if fixed != before:
                    lst[i] = fixed
                    return True, reason

        else:
            before = copy.deepcopy(group)
            fixed, reason = mitigate_condition(group, current_rule)
            if fixed != group:
                conditions[gi] = fixed
                return True, reason

    return False, ""


def save_mitigation_log(original_rule, fixed_rule, status, reason):
    os.makedirs("logs", exist_ok=True)

    file_path = "logs/mitigation_logs.csv"
    file_exists = os.path.isfile(file_path)

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "status",
                "reason",
                "original_rule",
                "fixed_rule"
            ])

        writer.writerow([
            status,
            reason,
            json.dumps(original_rule),
            json.dumps(fixed_rule)
        ])


def mitigate_rule(rule):
    original_rule = copy.deepcopy(rule)
    current_rule = copy.deepcopy(rule)

    previous_rule = None
    last_reason = ""

    while True:
        valid, message = check_hallucination(current_rule)

        if valid:
            save_mitigation_log(
                original_rule,
                current_rule,
                "success",
                last_reason
            )
            return current_rule, "mitigated_successfully"

        if previous_rule == current_rule:
            save_mitigation_log(
                original_rule,
                current_rule,
                "failed",
                "No further improvement possible"
            )
            return current_rule, "mitigation_failed"

        previous_rule = copy.deepcopy(current_rule)
        changed = False

        for i, action in enumerate(current_rule.get("actions", [])):
            fixed_action, reason = mitigate_action(action)

            if fixed_action != action:
                current_rule["actions"][i] = fixed_action
                changed = True
                last_reason = reason
                print("Mitigation:", reason)
                break

        if not changed:
            cond_changed, cond_reason = _mitigate_first_condition(current_rule)
            if cond_changed:
                changed = True
                last_reason = cond_reason
                print("Mitigation:", cond_reason)

        if not changed:
            save_mitigation_log(
                original_rule,
                current_rule,
                "failed",
                message
            )
            return current_rule, "mitigation_failed"