"""Distinguish unchanged prepared demos from correspondence edited by the sender."""

from app.mail_templates import templates


def uses_custom_intake(message):
    if message.template_key == "CUSTOM":
        return True
    template = next(t for t in templates() if t.key == message.template_key)
    return template.kind == "initial" and (
        any(
            getattr(message, key) != getattr(template, key) for key in ("sender", "subject", "body")
        )
        or {a["key"] for a in message.attachments if not a.get("upload_id")}
        != {a["key"] for a in template.attachments}
    )
