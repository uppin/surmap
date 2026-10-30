"""Offline segmentation benchmark for the disaster-block survey.

The scoring frame and clock live in `conventions.DEFAULT_SCORING`.
Metrics read that record; they do not pick a frame of their own.
"""

from surmap.segbench.conventions import DEFAULT_SCORING, ScoringFrame

__all__ = ["DEFAULT_SCORING", "ScoringFrame"]
