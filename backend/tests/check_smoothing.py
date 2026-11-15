"""Offline checks for aspect smoothing. Run: python -m tests.check_smoothing"""
from app.services.smoothing import smooth

assert abs(smooth(10, -0.8, 0.2, 10) - (-0.3)) < 1e-9            # equal weight: halfway
assert abs(smooth(1, -1.0, 0.0, 10) - (-1 / 11)) < 1e-9          # one mention barely moves the overall mean
assert abs(smooth(1000, 0.5, 0.0, 10) - 0.5 * 1000 / 1010) < 1e-9
assert smooth(0, 0.9, 0.1, 10) == 0.1                            # no mentions: the overall mean
print("smoothing checks passed")
