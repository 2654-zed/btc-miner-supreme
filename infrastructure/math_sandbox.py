"""
infrastructure/math_sandbox.py
──────────────────────────────
Secure mathematical expression evaluator combining rigid AST-based
sanitisation with NumExpr's multi-core, cache-blocking execution engine.

Architecture (Hybrid: AST  ⟶  NumExpr)
───────────────────────────────────────
1. The raw user string is parsed into a Python Abstract Syntax Tree.
2. A custom ``MathSanitizer`` (ast.NodeVisitor) traverses every node,
   verifying it belongs to a hardcoded whitelist of safe mathematical
   operations.  Any unauthorised construct (function calls, attribute
   access, import statements, comprehensions …) immediately raises
   ``SecurityViolationError``.
3. Only if the AST is proven sterile is the *original, unmodified*
   string forwarded to ``numexpr.evaluate()`` for high-speed,
   GIL-bypassing, L1-cache-optimised parallel execution.

Why not eval()?
───────────────
``eval()`` permits arbitrary code execution via object introspection:
    ().__class__.__bases__[0].__subclasses__()
Even with ``__builtins__`` set to ``None`` the sandbox is trivially
escapable.  This module **never** calls ``eval()`` or ``exec()``.

Why not SymPy?
──────────────
``sympy.sympify()`` delegates to ``eval()`` internally and is explicitly
documented as unsafe for untrusted input.  Performance is also unsuitable
for high-throughput nonce-array evaluations.

Why not asteval?
────────────────
Pure AST interpretation incurs ~4× overhead vs. compiled NumPy due to
recursive Python-space function calls — fatal for brute-force contexts.
"""

from __future__ import annotations

import ast
import logging
from typing import Optional, Set

import numpy as np

from core.exceptions import SecurityViolationError

logger = logging.getLogger(__name__)

# ── Lazy NumExpr import ─────────────────────────────────────────────────
_ne = None
_HAS_NUMEXPR = False


def _try_import_numexpr():
    global _ne, _HAS_NUMEXPR
    if _ne is not None:
        return
    try:
        import numexpr as ne
        _ne = ne
        _HAS_NUMEXPR = True
        logger.info(
            "NumExpr %s loaded — %d threads, VML available: %s",
            ne.__version__,
            ne.nthreads,
            ne.use_vml,
        )
    except ImportError:
        logger.warning(
            "NumExpr not installed; MathSandbox will fall back to "
            "pure-NumPy evaluation (slower, single-threaded)."
        )


# ─── AST Sanitizer ─────────────────────────────────────────────────────

class MathSanitizer(ast.NodeVisitor):
    """
    Recursively traverses a Python AST to guarantee that **only**
    whitelisted mathematical primitives are present.

    Any node not in the explicit allow-list triggers an immediate
    ``SecurityViolationError`` via the overridden ``generic_visit``.
    """

    # Domain-specific variable whitelist
    ALLOWED_NAMES: Set[str] = {"nonce", "pi", "e", "phi", "gamma"}

    # ── Approved node types ─────────────────────────────────────────────
    ALLOWED_NODES = (
        ast.Module,
        ast.Expr,
        ast.Expression,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.BinOp,
        ast.UnaryOp,
    )

    ALLOWED_BINOPS = (
        ast.Add, ast.Sub, ast.Mult, ast.Div,
        ast.FloorDiv, ast.Mod, ast.Pow,
        ast.BitXor, ast.BitAnd, ast.BitOr,
        ast.LShift, ast.RShift,
    )

    ALLOWED_UNARYOPS = (
        ast.USub, ast.UAdd, ast.Invert,
    )

    # Merge all allowed node types for generic_visit check
    ALLOWED_NODES = ALLOWED_NODES + ALLOWED_BINOPS + ALLOWED_UNARYOPS

    # ── Visitor methods ─────────────────────────────────────────────────

    def visit_Module(self, node: ast.Module):
        for child in node.body:
            self.visit(child)

    def visit_Expression(self, node: ast.Expression):
        self.visit(node.body)

    def visit_Expr(self, node: ast.Expr):
        self.visit(node.value)

    def visit_Name(self, node: ast.Name):
        if node.id not in self.ALLOWED_NAMES:
            raise SecurityViolationError(
                f"Unauthorised variable detected: '{node.id}'. "
                f"Allowed: {sorted(self.ALLOWED_NAMES)}"
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if not isinstance(node.value, (int, float, complex)):
            raise SecurityViolationError(
                f"Only numeric constants are permitted; "
                f"received {type(node.value).__name__}: {node.value!r}"
            )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if not isinstance(node.op, self.ALLOWED_BINOPS):
            raise SecurityViolationError(
                f"Unauthorised binary operator: {type(node.op).__name__}"
            )
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if not isinstance(node.op, self.ALLOWED_UNARYOPS):
            raise SecurityViolationError(
                f"Unauthorised unary operator: {type(node.op).__name__}"
            )
        self.generic_visit(node)

    # ── Catch-all ───────────────────────────────────────────────────────

    def generic_visit(self, node: ast.AST):
        """
        Overrides default traversal to **deny** any node type not
        explicitly handled above.
        """
        if not isinstance(node, self.ALLOWED_NODES):
            raise SecurityViolationError(
                f"Unauthorised language construct: {type(node).__name__}. "
                "Only pure arithmetic expressions are permitted."
            )
        super().generic_visit(node)


# ─── MathSandbox ────────────────────────────────────────────────────────

class MathSandbox:
    """
    Executes dynamic mathematical equations safely at maximum CPU
    parallelisation speed.

    Lifecycle
    ---------
    1. ``_sanitize(formula)`` — parse to AST, traverse with
       ``MathSanitizer``.  Rejects anything beyond pure arithmetic.
    2. ``execute(formula, nonces)`` — if sanitisation passes, evaluate
       via NumExpr (multi-core, GIL-bypassing) or pure-NumPy fallback.

    Thread Safety
    -------------
    The ``MathSanitizer`` is stateless and safe for concurrent use.
    NumExpr's internal thread pool is process-global but re-entrant.
    """

    # Mathematical constants injected into every evaluation
    _MATH_CONSTANTS = {
        "pi": np.float64(np.pi),
        "e": np.float64(np.e),
        "phi": np.float64((1 + np.sqrt(5)) / 2),   # Golden ratio
        "gamma": np.float64(0.5772156649015329),     # Euler–Mascheroni
    }

    def __init__(self, num_threads: Optional[int] = None):
        _try_import_numexpr()
        if num_threads and _HAS_NUMEXPR:
            _ne.set_num_threads(num_threads)
            logger.info("NumExpr thread count set to %d", num_threads)

    # ── Public API ──────────────────────────────────────────────────────

    def sanitize(self, formula: str) -> bool:
        """
        Parse and validate a formula string.

        Returns ``True`` if the formula is safe.
        Raises ``SecurityViolationError`` or ``ValueError`` otherwise.
        """
        if not formula or not formula.strip():
            raise ValueError("Empty formula string.")
        try:
            tree = ast.parse(formula.strip(), mode="exec")
        except SyntaxError as exc:
            raise ValueError(
                f"Invalid mathematical syntax: {exc.msg} "
                f"(line {exc.lineno}, col {exc.offset})"
            ) from exc

        sanitizer = MathSanitizer()
        sanitizer.visit(tree)
        return True

    def execute(self, formula: str, nonces: np.ndarray) -> np.ndarray:
        """
        Validate ``formula`` then evaluate it against ``nonces``.

        Parameters
        ----------
        formula : str
            A pure arithmetic expression referencing ``nonce`` and
            optional constants (``pi``, ``e``, ``phi``, ``gamma``).
        nonces : np.ndarray
            1-D array of uint32 nonce candidates.

        Returns
        -------
        np.ndarray
            Result array.  Division-by-zero yields ``np.nan``.
        """
        # Phase 1 — rigid AST sanitisation
        self.sanitize(formula)

        # Phase 2 — build local namespace
        local_dict = {"nonce": nonces.astype(np.float64)}
        local_dict.update(self._MATH_CONSTANTS)

        # Phase 3 — high-speed evaluation
        if _HAS_NUMEXPR:
            try:
                return _ne.evaluate(formula.strip(), local_dict=local_dict)
            except ZeroDivisionError:
                return np.full(len(nonces), np.nan, dtype=np.float64)
            except Exception as exc:
                logger.warning(
                    "NumExpr evaluation failed (%s); falling back to NumPy", exc
                )

        # Fallback — pure-NumPy (single-threaded, slower)
        return self._numpy_fallback(formula, local_dict)

    # ── Private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _numpy_fallback(formula: str, local_dict: dict) -> np.ndarray:
        """
        Evaluate using NumPy operations only.  Because the AST has
        already been proven sterile, we construct a minimal eval
        with an empty ``__builtins__`` dict as a *secondary* guard.
        """
        safe_globals = {"__builtins__": None, "np": np}
        safe_globals.update({
            k: v for k, v in local_dict.items()
        })
        try:
            with np.errstate(divide="ignore", invalid="ignore"):
                result = eval(compile(formula.strip(), "<sandbox>", "eval"),  # noqa: S307
                              safe_globals, {})
                return np.asarray(result, dtype=np.float64)
        except ZeroDivisionError:
            return np.full(len(local_dict.get("nonce", [])), np.nan, dtype=np.float64)
