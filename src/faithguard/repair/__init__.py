"""Repair: rule-only v0 now; the trained edit-program model arrives in phase 4."""

from faithguard.repair.gate import gate
from faithguard.repair.rules import repair, write_program

__all__ = ["gate", "repair", "write_program"]
