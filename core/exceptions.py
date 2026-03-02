"""
core/exceptions.py
──────────────────
Custom exception hierarchy for the orchestration engine.
"""


class SecurityViolationError(Exception):
    """
    Raised when the AST-based sanitizer detects an unauthorised or
    potentially malicious construct in a user-supplied formula string.

    Examples of trigger conditions:
      • Function calls (ast.Call)
      • Attribute access (ast.Attribute)
      • Import statements (ast.Import / ast.ImportFrom)
      • Dictionary / list / set comprehensions
      • Any variable name not in the explicit whitelist
    """
    pass


class HardwareRoutingError(Exception):
    """
    Raised when a workload is dispatched to a hardware target that
    cannot satisfy the request (e.g., dynamic strings → FPGA).
    """
    pass


class OrchestrationError(Exception):
    """
    Generic orchestration-level error for pipeline stalls, queue drain
    failures, or strategy hot-swap faults.
    """
    pass


class FormulaValidationError(ValueError):
    """
    Raised when a formula string fails Pydantic or syntactic validation
    before reaching the AST sanitizer.
    """
    pass
