"""Offline checks for the fine-tuning helpers. Run from backend: python -m tests.check_finetune"""
import importlib.util
import sys
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "ml" / "finetune.py"
spec = importlib.util.spec_from_file_location("finetune", p)
ft = importlib.util.module_from_spec(spec)
sys.modules["finetune"] = ft
spec.loader.exec_module(ft)

assert [ft.label3({"star": s, "pol": -1}) for s in range(5)] == [0, 0, 1, 2, 2]
assert [ft.label3({"star": -1, "pol": q}) for q in range(3)] == [0, 1, 2]
rows = [{"star": s % 5, "pol": -1, "text": str(i)} for i, s in enumerate(range(1000))]
chosen = ft.pick(rows, 300)
assert len(chosen) == 300 and sum(ft.label3(r) == 1 for r in chosen) >= 90 and ft.pick(rows, 300) == chosen
w = ft.class_weights([0] * 700 + [1] * 100 + [2] * 200)
assert abs(sum(w) / 3 - 1) < 1e-9 and w[1] > w[2] > w[0]
assert ft.macro_f1([0, 1, 2, 2], [0, 1, 2, 2]) == 1.0 and ft.macro_f1([0, 0, 2, 2], [2, 2, 0, 0]) == 0.0
print("fine-tune helper checks passed")
