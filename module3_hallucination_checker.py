import csv


def load_rooms():
    rooms = []
    with open("data/rooms.csv", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rooms.append(row["room"])
    return rooms


def load_device_catalog():
    catalog = {}

    with open("data/devices.csv", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            room = row["room"]
            device = row["device"]
            actions = row["allowed_actions"].split(";")

            if room not in catalog:
                catalog[room] = {}

            catalog[room][device] = actions

    return catalog


def load_sensor_catalog():
    sensors = []

    with open("data/sensors.csv", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            sensors.append(row)

    return sensors


ROOMS = load_rooms()
DEVICE_CATALOG = load_device_catalog()
SENSOR_CATALOG = load_sensor_catalog()


def normalize_location(location):
    if location in ["house", "home", "whole_house"]:
        return "all"
    return location


def check_action_for_all_rooms(device, act):
    found_device = False

    for room in ROOMS:
        if device in DEVICE_CATALOG.get(room, {}):
            found_device = True
            allowed_actions = DEVICE_CATALOG[room][device]

            if act not in allowed_actions:
                return False, f"Action '{act}' not allowed for device '{device}' in '{room}'"

            print(f"Valid Action → {act} {device} in {room}")

    if not found_device:
        return False, f"Device '{device}' does not exist in any room"

    return True, "Valid action for all rooms"


def check_action(action):
    room = action.get("room")
    device = action.get("device")
    act = action.get("action")

    room = normalize_location(room)

    if room not in ROOMS and room != "all":
        return False, f"Room '{room}' does not exist"

    if room == "all":
        return check_action_for_all_rooms(device, act)

    if device not in DEVICE_CATALOG.get(room, {}):
        return False, f"Device '{device}' not in room '{room}'"

    allowed_actions = DEVICE_CATALOG[room][device]

    if act not in allowed_actions:
        return False, f"Action '{act}' not allowed for device '{device}'"

    print(f"Valid Action → {act} {device} in {room}")
    return True, "Valid action"


def find_sensor(sensor, location):
    location = normalize_location(location)

    for s in SENSOR_CATALOG:
        sensor_name = s["sensor"]
        sensor_location = normalize_location(s["location"])

        if sensor_name == sensor:
            if sensor_location == location or sensor_location == "all":
                return s

    return None


def check_single_condition(condition):
    sensor = condition.get("condition_type") or condition.get("sensor")
    location = (
        condition.get("location")
        or condition.get("room")
        or condition.get("scope")
        or "all"
    )
    operator = condition.get("operator")
    value = condition.get("value")

    location = normalize_location(location)

    sensor_match = find_sensor(sensor, location)

    if not sensor_match:
        return False, f"Sensor '{sensor}' not available in '{location}'"

    allowed_operators = sensor_match["allowed_operators"].split(";")

    if operator not in allowed_operators:
        return False, f"Operator '{operator}' not allowed for sensor '{sensor}'"

    min_value = sensor_match.get("min_value", "")
    max_value = sensor_match.get("max_value", "")

    if min_value != "" and max_value != "" and value is not None:
        try:
            numeric_value = float(value)
            min_v = float(min_value)
            max_v = float(max_value)

            if numeric_value < min_v or numeric_value > max_v:
                return False, f"Value '{value}' out of range for sensor '{sensor}'"

        except ValueError:
            return False, f"Value '{value}' is invalid for sensor '{sensor}'"

    print(f"✅ Valid Condition → {sensor} {operator} {value} in {location}")
    return True, "Valid condition"


def check_conditions(rule):
    conditions = rule.get("conditions", [])

    if not conditions:
        return True, "No conditions"

    for group in conditions:
        if "any" in group:
            condition_items = group["any"]
        elif "all" in group:
            condition_items = group["all"]
        else:
            condition_items = [group]

        for condition in condition_items:
            valid, message = check_single_condition(condition)

            if not valid:
                return False, message

    return True, "All conditions valid"


def check_hallucination(rule):
    print("\nChecking actions...\n")

    for action in rule.get("actions", []):
        valid, message = check_action(action)

        if not valid:
            print(f"{message}")
            return False, message

    print("\nChecking conditions...\n")

    valid, message = check_conditions(rule)

    if not valid:
        print(f"{message}")
        return False, message

    print("\nAll actions and conditions are valid")
    return True, "All actions and conditions valid"