"""Offline checks for the results CSV. Run: python -m tests.check_export_csv"""
import csv
import io

from app.services.export_csv import BASE, build_csv, safe_cell, short_model, vote_label

assert vote_label(0.5, 0.3, 0.2) == "neg" and vote_label(0.2, 0.5, 0.3) == "neu" and vote_label(0.1, 0.2, 0.7) == "pos"
assert vote_label(0.4, 0.4, 0.2) == "neg"                      # ties: negative first, same rule as fusion
assert short_model("cardiffnlp/twitter-roberta-base-sentiment-latest") == "twitter-roberta-base-sentiment-latest"
assert safe_cell("=SUM(A1)") == chr(39) + "=SUM(A1)" and safe_cell("@x") == chr(39) + "@x" and safe_cell("-5") == "-5" and safe_cell(None) == ""
assert safe_cell("Great product") == "Great product"

rows = [(1, "Lip balm", "5", 5.0, "en", None, "Loved it, really", 0.0, "pos", 0.9, 4.9, 4.7, -0.3, None),
        (2, "Lip balm", "1", 1.0, "hi", None, "=HYPERLINK(\"x\")", 0.0, "neg", 0.8, 1.2, None, None, None)]
votes = {1: {"roberta": "pos", "nlptown": "pos"}, 2: {"xlmr": "neg"}}
text = build_csv(rows, votes)
assert text.startswith(chr(0xFEFF))
parsed = list(csv.reader(io.StringIO(text.lstrip(chr(0xFEFF)))))
assert parsed[0] == BASE + ["vote_nlptown", "vote_roberta", "vote_xlmr"], parsed[0]
assert parsed[1][6] == "Loved it, really" and parsed[1][-3:] == ["pos", "pos", ""], parsed[1]
assert parsed[2][6].startswith(chr(39) + "=") and parsed[2][-1] == "neg"
assert len(parsed) == 3 and all(len(r) == len(parsed[0]) for r in parsed)
print("results CSV checks passed")
