"""B4 reminders: placeholder until the scheduler/worker lands. Never claims delivery."""


def confirmation_note(client, scope, item) -> str:
    if item.reminder is None or item.reminder.kind == "none":
        return "No reminders were requested."
    return ("Your reminder preference is saved, but reminder delivery is not available on this server yet, "
            "so no reminders will be sent.")
