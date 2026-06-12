"""Operational training primitives for governed Brain autonomy.

This package does not train model weights and does not write semantic memory or
FAISS artifacts. It provides typed records for lessons, mistakes, promotion
gates, and teacher/student cycle summaries.
"""

from .lesson_card import LessonCard
from .mistake_registry import MistakeEntry, MistakeRegistry
from .promotion_gates import PromotionGate
from .teacher_student_loop import TeacherStudentCycle, TeacherStudentLoop

__all__ = [
    "LessonCard",
    "MistakeEntry",
    "MistakeRegistry",
    "PromotionGate",
    "TeacherStudentCycle",
    "TeacherStudentLoop",
]
