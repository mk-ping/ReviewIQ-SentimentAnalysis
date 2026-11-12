RULES = {
    "packaging": ("Review the closure or pump design and ask the supplier for a fix or a replacement part", "Packaging and supplier quality"),
    "delivery": ("Audit the courier and dispatch process and set delivery-time targets", "Logistics"),
    "price": ("Compare price and pack size with competitors and make the value clearer on the listing", "Pricing and marketing"),
    "quality": ("Inspect the affected batches and tighten the quality checks before dispatch", "Quality and manufacturing"),
    "durability": ("Run durability tests and review the materials used", "Product and R&D"),
    "scent": ("Review the fragrance or describe the scent more accurately on the listing", "Product and marketing"),
    "texture": ("Review the formulation texture and test it with a small customer group", "Product and R&D"),
    "size and fit": ("Correct the size guide or the sizing itself", "Product and merchandising"),
    "ease of use": ("Improve the instructions or the dispensing mechanism", "Product and design"),
    "appearance": ("Check that colour and finish match the listing photos", "Design and marketing"),
    "effectiveness": ("Compare the claimed results with customer feedback and review the formulation", "Product and R&D"),
    "customer service": ("Set response-time targets and retrain the support team on the repeated complaints", "Customer support"),
}
DEFAULT = ("Read the evidence reviews and decide on an owner", "Manager")


def rule_for(aspect: str) -> tuple[str, str]:
    return RULES.get(aspect, DEFAULT)
