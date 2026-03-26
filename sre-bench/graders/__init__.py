"""Graders for SREBench tasks."""
from .easy import grade_easy
from .medium import grade_medium
from .hard import grade_hard

__all__ = ["grade_easy", "grade_medium", "grade_hard"]
