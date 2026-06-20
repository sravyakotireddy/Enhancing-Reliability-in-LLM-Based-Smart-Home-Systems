from module1_parser import run_module1
from module2_rule_generator import run_module2
from module3_hallucination_checker import check_hallucination
from module4_mitigation import mitigate_rule
from module5_execution import run_execution


ALLOWED_USERS = ["father", "mother", "son"]


def run_pipeline(user_id, command):
    if command.lower() == "exit":
        return "exit"

    parsed = run_module1(user_id, command)
    # print("\nModule 1 - Parsed Command:")
    # print(parsed)

    if parsed.get("type") == "unknown":
        print("\nNot a smart home command. Ignored.")
        return parsed

    if parsed.get("type") == "preference":
        print("\nPersonal preference saved.")
        return parsed

    rule = run_module2(parsed)
    # print("\nModule 2 - Generated Rule:")
    # print(rule)

    valid, message = check_hallucination(rule)

    if valid:
        print("\nRule is valid.")
        run_execution(rule)

    else:
        print("\nHallucination detected:")
        print(message)

        print("\nTrying mitigation...")
        fixed_rule, status = mitigate_rule(rule)

        if status == "mitigated_successfully":
            print("\nMitigation successful.")
            # print("\nFixed Rule:")
            # print(fixed_rule)

            run_execution(fixed_rule)

        else:
            print("\nMitigation failed.")
            print("\nInvalid command. Need user clarification.")

    return parsed


if __name__ == "__main__":
    while True:
        user_id = input("\nEnter user (father/mother/son): ").strip().lower()

        if user_id not in ALLOWED_USERS:
            print("Invalid user. Please enter father, mother, or son.")
            continue

        command = input("Enter command: ")

        if command.lower() == "exit":
            print("Stopped.")
            break

        run_pipeline(user_id, command)