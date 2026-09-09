"""
Category-Specific Requirement Schemas.
Enforces hierarchical requirement collection:
  - critical: Must-have gates (cannot recommend without matching)
  - important: Key differentiator fields
  - optional: Nice-to-have features
"""
from typing import Dict, List, Any

REQUIREMENT_SCHEMAS: Dict[str, Dict[str, List[str]]] = {
    "technical_cad": {
        "critical": [
            "print_size",
        ],
        "important": [
            "scan_required",
            "daily_volume",
        ],
        "optional": [
            "connectivity",
            "ink_capacity",
        ]
    },
    "office_enterprise": {
        "critical": [
            "daily_volume",
        ],
        "important": [],
        "optional": [
            "speed",
            "scan_required",
            "duplex",
            "network",
        ]
    },
    "scanner": {
        "critical": [
            "document_type",
        ],
        "important": [
            "daily_volume",
        ],
        "optional": [
            "duplex",
            "network",
        ]
    },


    "photo_booth": {
        "critical": [
            "print_size",
        ],
        "important": [
            "print_volume",
        ],
        "optional": [
            "portability",
        ]
    },
    "photo_fine_art": {
        "critical": [
            "print_size",
        ],
        "important": [
            "color_gamut",
        ],
        "optional": [
            "roll_support",
        ]
    },
    "consumable": {
        "critical": [
            "printer_model",
        ],
        "important": [],
        "optional": []
    }
}

QUESTIONS_BY_FIELD: Dict[str, Dict[str, Any]] = {
    "print_size": {
        "question": "What maximum drawing or print size do you normally need?",
        "pills": ["24-inch (A1)", "36-inch (A0)"]
    },
    "scan_required": {
        "question": "Do you need scanning as well, or printing only?",
        "pills": ["Yes, Need Scanner", "No, Print Only"]
    },
    "daily_volume": {
        "question": "Approximately how many drawings or pages do you print per day?",
        "pills": ["Low (1-10)", "Medium (10-50)", "High Volume (50+)"]
    },
    "speed": {
        "question": "Approximately how many pages do you print per day, or what speed do you need?",
        "pills": ["Standard Office (40-55 ppm)", "High Volume Production (60-100 ppm)", "Compact WorkForce"]
    },
    "printer_model": {
        "question": "Which printer or scanner model do you need consumables for?",
        "pills": ["SC-P900", "SC-T3100", "SC-F100", "SC-P700", "WF-C20600"]
    },
    "document_type": {
        "question": "What types of documents do you primarily need to scan?",
        "pills": ["Standard Documents / Invoices", "Passports & IDs", "Large Format Drawings"]
    }
}


def get_question_for_field(field: str, category: str = None) -> Dict[str, Any]:
    """Returns the question and suggestion chips tailored to the specific product category."""
    if field == "print_size":
        if category == "photo_booth":
            return {
                "question": "What photo print sizes do you primarily require?",
                "pills": ["4x6\" Standard", "5x7\"", "6x8\" Strips"]
            }
        elif category == "photo_fine_art":
            return {
                "question": "What maximum print width do you require for photo & fine art?",
                "pills": ["13-inch (A3+)", "17-inch (A2+)", "24-inch to 44-inch Production"]
            }
        elif category == "technical_cad":
            return {
                "question": "What maximum drawing size do you normally print?",
                "pills": ["24-inch (A1)", "36-inch (A0)"]
            }

    if field == "daily_volume":
        if category == "office_enterprise":
            return {
                "question": "Approximately how many pages do you print per day?",
                "pills": ["Low (1-50 pages/day)", "Medium (50-200 pages/day)", "High Volume (200+ pages/day)"]
            }
        elif category == "technical_cad":
            return {
                "question": "Roughly how many drawings do you print per day?",
                "pills": ["Low (1-10)", "Medium (10-50)", "High Volume (50+)"]
            }

    return QUESTIONS_BY_FIELD.get(field, {
        "question": f"What are your requirements for {field.replace('_', ' ')}?",
        "pills": []
    })

