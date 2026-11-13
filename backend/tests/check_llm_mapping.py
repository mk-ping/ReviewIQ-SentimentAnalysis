from app.services.llm_mapping import validate_mapping

header = ["Review", "Stars"]
raw = {"text": "Review", "rating": "Review", "zzz": "Stars", "date": "NotAColumn", "rating2": "Stars"}
assert validate_mapping(raw, header) == {"text": "Review"}, validate_mapping(raw, header)
assert validate_mapping({"text": "Review", "rating": "Stars"}, header) == {"text": "Review", "rating": "Stars"}
assert validate_mapping("not a dict", header) == {}
print("llm mapping validation passed")
