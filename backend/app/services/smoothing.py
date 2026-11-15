"""Aspect heatmap smoothing (final pipeline document, section 8): (n x cell mean + m x overall mean) / (n + m)."""


def smooth(n: int, cell_mean: float, overall_mean: float, m: int = 10) -> float:
    """Pulls a cell with few mentions toward the overall mean; a cell with many mentions barely moves."""
    return (n * cell_mean + m * overall_mean) / (n + m)
