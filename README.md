# Smart Home: Hallucinations and Mitigation

This project parses natural-language smart-home commands, builds rules, and **checks every rule against CSV catalogs** (`data/rooms.csv`, `data/devices.csv`, `data/sensors.csv`). When the model output does not match the real home, we treat that as a **hallucination** and try **mitigation** before rejecting or executing the command.

---

## Hallucination checks

Hallucination detection is **catalog-based validation**, not a separate ML model. Anything that fails these checks is reported as invalid (the message you see in the CLI or API is the hallucination detail).

### Actions (`check_action` / `check_action_for_all_rooms`)

| Check | Typical cause |
|--------|------------------|
| **Unknown room** | Room name is not in `rooms.csv` and is not `all` (e.g. parser used `unknown` as a placeholder). |
| **Wrong room for device** | Device exists in the home but not in the room named on the action. |
| **Unknown device in room** | Device id does not appear under that room in `devices.csv`. |
| **Invalid action** | Action is not listed in that row’s `allowed_actions`. |
| **Whole-house (`all`)** | For `room: "all"`, the device must exist in **at least one** room; for **each** room that lists that device, the action must be allowed there. |

### Conditions (`check_single_condition`)

| Check | Typical cause |
|--------|------------------|
| **Sensor / location** | Sensor is not defined for that location in `sensors.csv` (after normalizing `house` / `home` / `whole_house` → `all`). |
| **Operator** | Operator is not in that sensor’s `allowed_operators`. |
| **Value range** | Numeric value is outside `min_value` / `max_value` for that sensor. |
| **Value type** | Value cannot be interpreted as a number when a numeric range applies. |

Rules are invalid if **any** action fails or **any** condition in the rule’s condition groups fails.

---

## Mitigation types

Mitigation runs only when validation fails. It **mutates a copy of the rule** in small steps until validation passes or no further change is possible.

### Action mitigation (`mitigate_action`)

Applied in order until one strategy changes the action:

1. **Device alias** — Maps common LLM names to catalog ids (e.g. `exhaust` → `exhaust_fan` via `DEVICE_ALIASES` in `module4_mitigation.py`).
2. **Unknown / missing room** — Infers a room from the **canonical** device id:
   - Only one room has that device → use it.
   - Device missing from catalog → cannot infer (needs catalog or alias fix).
   - User “presence” stub (`USER_PRESENCE`) prefers a room when the user is marked present and the device exists there.
   - Otherwise **command history** in `logs/command_logs.csv` (frequency / recency among candidate rooms).
   - If exactly **two** rooms still tie with no history/presence, picks the **first in home order** (`rooms.csv` order) and records that in the reason string.
3. **Sensor named as device** — If the “device” field matches a sensor that has `related_devices` in `sensors.csv`, rewrites to an actual device in the same room (and may normalize the action, e.g. toward `turn_on`).
4. **Wrong room, device exists elsewhere** — If the room is valid but the device is not in that room, moves the action to the only catalog room that has the device, or uses the same **infer_room** logic when multiple rooms apply.

If nothing applies, the action is unchanged and mitigation may try **conditions** next.

### Condition mitigation (`mitigate_condition`)

- Parses a **raw string** condition (e.g. `temperature > 30`) into `sensor`, `operator`, `value`.
- **Sensor token aliases** (e.g. `temp` → `temperature`, `gas` → `gas_sensor`).
- Normalizes operators (e.g. `=` → `==`).
- **Location**: fills missing location from the first action’s room, or `all` when the action room is unknown.
- **Value clamping**: soft bounds for temperature/humidity, then clamp to catalog min/max when defined.

### Mitigation loop (`mitigate_rule`)

Repeatedly runs `check_hallucination`; on failure, fixes **one** action (first changeable) or **one** condition (first changeable group item), then re-validates. Stops when the rule is valid or the rule no longer changes (**mitigation failed**).

### Logged outcomes (`logs/mitigation_logs.csv`)

- **`success`** — Rule became valid (either unchanged from the start in that call path, or fixed and then validated).
- **`failed`** — No further automatic fix; the command should be clarified or rephrased by the user.

API / CLI copy uses string statuses such as **`mitigated_successfully`** and **`mitigation_failed`** for the last mitigation pass.

---

## How to run

Prerequisites: **Python 3.8+**, **Node.js** (for the dashboard), **`pip install -r requirements.txt`**, **`npm install`** inside `frontend/`, and a **`.env`** in the project root with `OPENAI_API_KEY=` for LLM parsing and rule generation.

Always run commands from the **repository root** (where `data/` and `logs/` resolve correctly).

### One command: API + dashboard (`run.py`)

Starts **FastAPI** on `http://127.0.0.1:8000` and **Vite** on `http://127.0.0.1:5173` in one terminal. Stop with **Ctrl+C**.

```bash
python run.py
```

Options:

```bash
python run.py --help
python run.py --backend-only
python run.py --frontend-only
python run.py --no-reload
python run.py --port 8000
```

### CLI pipeline only (`run_pipeline.py`)

Interactive terminal: choose user (`father` / `mother` / `son`), enter commands, type `exit` to quit.

```bash
python run_pipeline.py
```

### Backend or frontend alone

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
cd frontend && npm run dev
```

Optional: set `VITE_API_URL` if the API is not on `http://localhost:8000`.

### Tests

```bash
python -m pytest test/
```

---

## License

Specify your license here.
