"""
Category Requirement Schemas for Kepler Tech SalesAI.
Enforces mandatory and optional requirement collection per approved category:
- office_printer
- technical_large_format
- photography_large_format
- citizen_photo

Rules:
- Ask strictly one missing mandatory question at a time.
- Never ask again for already-answered requirements.
- Extract all provided requirements in a turn.
"""
from typing import Dict, List, Any, Optional

ALLOWED_PRODUCT_LINES = {
    "workforce_pro",
    "workforce_enterprise",
    "surecolor_t",
    "surecolor_p",
    "citizen",
    "unspecified",
}

CATEGORY_REQUIREMENT_SCHEMAS: Dict[str, Dict[str, List[str]]] = {
    "office_printer": {
        "mandatory": [
            "paper_size",
            "daily_volume",
        ],
        "optional": [
            "product_line",
            "colour_mode",
            "functions",
            "fax_required",
            "duplex_required",
            "finishing_required",
            "paper_capacity",
            "connectivity",
        ]
    },
    "technical_large_format": {
        "mandatory": [
            "application",
            "print_width",
            "scanner_required",
            "daily_volume",
        ],
        "optional": [
            "product_line",
            "dual_roll_required",
            "postscript_required",
            "security_required",
            "colour_requirements",
        ]
    },
    "photography_large_format": {
        "mandatory": [
            "print_width",
            "daily_volume",
        ],
        "optional": [
            "product_line",
            "application",
            "scanner_required",
            "dual_roll_required",
            "spectro_required",
            "roll_printing_required",
            "colour_accuracy_priority",
            "media_types",
        ]
    },
    "citizen_photo": {
        "mandatory": [
            "print_sizes",
            "daily_volume",
        ],
        "optional": [
            "product_line",
            "usage_environment",
            "portability_required",
            "available_space",
            "finish_required",
            "unattended_operation",
        ]
    }
}

QUESTIONS_BY_FIELD: Dict[str, Dict[str, Any]] = {
    "product_line": {
        "question": "Which product line do you prefer—WorkForce Pro or WorkForce Enterprise?",
        "pills": ["WorkForce Pro", "WorkForce Enterprise", "Any / Either"]
    },
    # Office printers
    "paper_size": {
        "question": "What maximum document size do you need—standard A4 or large A3?",
        "pills": ["A4 Standard", "A3 Large Format"]
    },
    "colour_mode": {
        "question": "Do you need full colour printing or monochrome only?",
        "pills": ["Colour Printing", "Monochrome Only"]
    },
    "functions": {
        "question": "Do you require multifunction capabilities (printing, scanning, copying) or dedicated print-only?",
        "pills": ["Multifunction (Print/Scan/Copy)", "Print Only"]
    },
    "daily_volume": {
        "question": "Approximately how many pages, drawings, or photos do you produce per day?",
        "pills": ["Low (under 50/day)", "Medium (50–200/day)", "High Volume (200+/day)"]
    },

    # Technical large-format
    "application": {
        "question": "What is your primary application—CAD/engineering drawings, GIS mapping, or presentation posters?",
        "pills": ["CAD Drawings", "GIS & Regional Maps", "AEC Blueprints", "Posters & Line Art"]
    },
    "print_width": {
        "question": "What maximum roll width do you require—24-inch (A1), 36-inch (A0), or 44-inch?",
        "pills": ["24-inch (A1)", "36-inch (A0)", "44-inch Wide"]
    },
    "scanner_required": {
        "question": "Do you need an integrated wide-format scanner for copying blueprints, or print-only?",
        "pills": ["Yes, with Scanner", "No, Print Only"]
    },

    # Photography / Fine art
    "photography_print_width": {
        "question": "What print width do you need—compact 13-inch (A3+), 17-inch (A2+), 24-inch, 44-inch, or 64-inch?",
        "pills": ["13-inch (A3+)", "17-inch (A2+)", "24-inch Professional", "44-inch Fine Art", "64-inch Production"]
    },

    # Citizen photo
    "print_sizes": {
        "question": "Which photo print dimensions do you need (e.g., 4×6″, 6×8″, or 8×10″/8×12″)?",
        "pills": ["Compact 4x4 / 4.5x8", "Standard 4x6 & 6x8", "Large 8x10 & 8x12"]
    },
    "usage_environment": {
        "question": "What is your operating environment—mobile photo booth, retail kiosk, or studio portraiture?",
        "pills": ["Mobile Photo Booth", "Unattended Retail Kiosk", "Studio Portraiture"]
    }
}


def get_mandatory_fields(category: str) -> List[str]:
    """Returns the ordered list of mandatory fields for a category."""
    schema = CATEGORY_REQUIREMENT_SCHEMAS.get(category)
    return schema["mandatory"] if schema else []


def get_missing_mandatory_fields(category: str, requirements: Dict[str, Any]) -> List[str]:
    """Identifies which mandatory fields are still unanswered in requirements."""
    mandatory = get_mandatory_fields(category)
    missing = []
    for f in mandatory:
        # For technical CAD: all 24-inch models in catalogue are dedicated print-only
        if category == "technical_large_format" and f == "scanner_required" and requirements.get("print_width") == 24:
            continue
        val = requirements.get(f)
        if val is None or val == "" or val == []:
            missing.append(f)
    return missing


def get_next_question(category: str, missing_fields: List[str]) -> Optional[Dict[str, Any]]:
    """Returns the question and chips for strictly the FIRST missing mandatory field."""
    if not missing_fields:
        return None

    field_name = missing_fields[0]
    
    # Context-tailored questions
    if field_name == "print_width" and category == "photography_large_format":
        q_data = QUESTIONS_BY_FIELD["photography_print_width"]
    elif field_name == "daily_volume":
        if category == "citizen_photo":
            q_data = {
                "question": "Approximately how many photos do you print per event or per day?",
                "pills": ["Under 200 prints", "200–500 prints", "High Volume (700+ prints)"]
            }
        elif category == "technical_large_format":
            q_data = {
                "question": "Approximately how many drawings or plans do you print daily?",
                "pills": ["Low (1–15 drawings)", "Medium (15–50 drawings)", "High Volume (50+ drawings)"]
            }
        else:
            q_data = QUESTIONS_BY_FIELD["daily_volume"]
    else:
        q_data = QUESTIONS_BY_FIELD.get(field_name, {
            "question": f"What are your requirements for {field_name.replace('_', ' ')}?",
            "pills": []
        })

    return {
        "field": field_name,
        "question": q_data["question"],
        "pills": q_data.get("pills", [])
    }


class QualificationSchema:
    SCHEMAS = CATEGORY_REQUIREMENT_SCHEMAS
    QUESTIONS = QUESTIONS_BY_FIELD

    @staticmethod
    def get_missing_mandatory_fields(category: str, requirements: Dict[str, Any]) -> List[str]:
        return get_missing_mandatory_fields(category, requirements)

    @staticmethod
    def get_next_question(category: str, missing_fields: List[str]) -> Optional[Dict[str, Any]]:
        return get_next_question(category, missing_fields)


qualification_schema = QualificationSchema()
