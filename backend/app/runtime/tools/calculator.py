"""Safe arithmetic calculator tool for agents."""
import ast
import operator
from langchain_core.tools import tool

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {node.op}")
        return op_fn(_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {node.op}")
        return op_fn(_eval(node.operand))
    raise ValueError(f"Unsupported expression: {node}")


@tool
def calculator(expression: str) -> dict:
    """Evaluate a safe arithmetic expression and return the numeric result."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return {"result": result, "expression": expression}
    except Exception as exc:
        return {"error": str(exc), "expression": expression}
