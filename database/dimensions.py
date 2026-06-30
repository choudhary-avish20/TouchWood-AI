"""
Parses the dataset's `measurements` field into structured numeric fields. Absent fields to be NULL.
"""

import re
from dataclasses import dataclass

@dataclass
class ParsedDimensions:
    width_cm: float | None = None
    height_cm: float | None = None
    depth_cm: float | None = None       # "Length" in source data maps here
    diameter_cm: float | None = None


_DIM_PATTERN = re.compile(
    r"([A-Za-z][A-Za-z./ ]*?)\s*:\s*([\d,]+(?:\.\d+)?)\s*cm",
    re.IGNORECASE,
)

_LABEL_TO_FIELD = {
    "width": "width_cm",
    "height": "height_cm",
    "length": "depth_cm",  
    "diameter": "diameter_cm",
}


def parse_measurements(raw: str | None) -> ParsedDimensions:

    result = ParsedDimensions()
    if not raw or not isinstance(raw, str):
        return result

    for label, value in _DIM_PATTERN.findall(raw):
        label_key = label.strip().lower()
        field = _LABEL_TO_FIELD.get(label_key)
        if field is None:
            continue  
        try:
            numeric_value = float(value.replace(",", ""))
        except ValueError:
            continue
        setattr(result, field, numeric_value)

    return result


if __name__ == "__main__":
    test_cases = [
        'Burning time: 20 hr | Diameter: 7.5 cm (3 ") | Height: 7 cm (2 ¾ ")',
        'Diameter: 10.5 cm (4 ¼ ") | Height: 24 cm (9 ½ ") | Length: 21 cm (8 ¼ ") | Volume: 1.5 l (50.7 oz)',
        'Max. load/hook: 2 kg (4 lb) | Package quantity: 2 pack | Width: 4.5 cm (1 ¾ ") | Height: 8 cm (3 ¼ ")',
        'Width: 75 cm (29 1/2 ") | Height: 170 cm (66 7/8 ")',
        'Height: 9 cm (3 ½ ") | Length: 24 cm (9 ½ ")',
        None,
        '',
        'Picture, width: 140 cm (55 ") | Picture, height: 100 cm (39 ¼ ")',
    ]
    for case in test_cases:
        print(repr(case), "->", parse_measurements(case))
