REQUEST_FORM_FIELDS = [
    {
        "name": "name",
        "label": "Your name",
        "type": "text",
        "required": True,
        "placeholder": "Jane Smith",
    },
    {
        "name": "email",
        "label": "Email",
        "type": "email",
        "required": True,
        "placeholder": "you@example.com",
    },
    {
        "name": "company",
        "label": "Company",
        "type": "text",
        "required": False,
        "placeholder": "Company or project name",
    },
    {
        "name": "service",
        "label": "What do you need help with?",
        "type": "select",
        "required": True,
        "options": [
            "AWS / cloud setup",
            "Linux server support",
            "Terraform / infrastructure as code",
            "Docker / deployment help",
            "Automation / scripting",
            "Small business website",
            "Not sure yet",
        ],
    },
    {
        "name": "timeline",
        "label": "Timeline",
        "type": "select",
        "required": False,
        "options": ["ASAP", "This week", "This month", "Just exploring"],
    },
    {
        "name": "budget",
        "label": "Budget range",
        "type": "select",
        "required": False,
        "options": ["Not sure yet", "Under $500", "$500 - $1,500", "$1,500 - $5,000", "$5,000+"],
    },
    {
        "name": "message",
        "label": "Tell us about the request",
        "type": "textarea",
        "required": True,
        "placeholder": "Briefly describe what you want to build, fix, automate, or improve.",
    },
]


def public_form_config():
    return {"fields": REQUEST_FORM_FIELDS}


def select_options(field_name: str):
    for field in REQUEST_FORM_FIELDS:
        if field["name"] == field_name:
            return field.get("options", [])
    return []


def validate_request_payload(payload: dict):
    errors = {}
    cleaned = {}
    for field in REQUEST_FORM_FIELDS:
        name = field["name"]
        value = str(payload.get(name, "")).strip()
        if field.get("required") and not value:
            errors[name] = f"{field['label']} is required."
        if value and field.get("type") == "select" and field.get("options") and value not in field["options"]:
            errors[name] = f"Choose a valid value for {field['label']}."
        cleaned[name] = value
    email = cleaned.get("email", "")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        errors["email"] = "Enter a valid email address."
    return cleaned, errors
