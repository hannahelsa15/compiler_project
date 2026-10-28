"""
tree_ops.py - AST Operations: Traversals, ASCII Visualization, DOT/PNG Export, and Evaluation.

This module implements Phase 4 of the compiler pipeline:
  1. Tree Traversals (Inorder parenthesized, Preorder prefix, Postorder postfix)
  2. Terminal ASCII Art Pretty-Printing
  3. Graphviz DOT export and optional PNG rendering
  4. Tree-Walk Interpreter / Evaluator with variable environment support
"""

import os
import shutil
import subprocess
from typing import Dict, List, Optional, Set, Tuple, Union
from ast_builder import ASTNode, BinaryOpNode, NumberNode, UnaryOpNode, VariableNode


class EvaluationError(Exception):
    """Exception raised during AST evaluation (e.g., division by zero, undefined variable)."""
    pass


# ---------------------------------------------------------------------------
# 1. Tree Traversals
# ---------------------------------------------------------------------------

def inorder(node: ASTNode) -> str:
    """
    Inorder traversal producing fully parenthesized infix notation.
    Guarantees unambiguous reconstruction of operator associativity and precedence.

    Example:
        BinaryOpNode('+', NumberNode(2), BinaryOpNode('*', NumberNode(3), NumberNode(4)))
        -> "(2 + (3 * 4))"
    """
    if isinstance(node, NumberNode):
        return str(node.value)
    if isinstance(node, VariableNode):
        return node.name
    if isinstance(node, UnaryOpNode):
        return f"({node.op}{inorder(node.operand)})"
    if isinstance(node, BinaryOpNode):
        return f"({inorder(node.left)} {node.op} {inorder(node.right)})"
    raise TypeError(f"Unknown node type: {type(node)}")


def preorder(node: ASTNode) -> List[str]:
    """
    Preorder traversal producing a list of tokens in Prefix notation (Polish notation).
    Root -> Left -> Right
    """
    if isinstance(node, NumberNode):
        return [str(node.value)]
    if isinstance(node, VariableNode):
        return [node.name]
    if isinstance(node, UnaryOpNode):
        op_label = f"u{node.op}" if node.op in ('-', '+') else node.op
        return [op_label] + preorder(node.operand)
    if isinstance(node, BinaryOpNode):
        return [node.op] + preorder(node.left) + preorder(node.right)
    raise TypeError(f"Unknown node type: {type(node)}")


def postorder(node: ASTNode) -> List[str]:
    """
    Postorder traversal producing a list of tokens in Postfix notation (Reverse Polish Notation).
    Left -> Right -> Root
    """
    if isinstance(node, NumberNode):
        return [str(node.value)]
    if isinstance(node, VariableNode):
        return [node.name]
    if isinstance(node, UnaryOpNode):
        op_label = f"u{node.op}" if node.op in ('-', '+') else node.op
        return postorder(node.operand) + [op_label]
    if isinstance(node, BinaryOpNode):
        return postorder(node.left) + postorder(node.right) + [node.op]
    raise TypeError(f"Unknown node type: {type(node)}")


def preorder_str(node: ASTNode) -> str:
    """Convenience string representation of preorder traversal."""
    return " ".join(preorder(node))


def postorder_str(node: ASTNode) -> str:
    """Convenience string representation of postorder traversal."""
    return " ".join(postorder(node))


# ---------------------------------------------------------------------------
# 2. Terminal ASCII Art Pretty-Printer
# ---------------------------------------------------------------------------

def _node_label(node: ASTNode) -> str:
    """Returns human-readable label for terminal printing."""
    if isinstance(node, NumberNode):
        return f"Number({node.value})"
    if isinstance(node, VariableNode):
        return f"Variable({node.name})"
    if isinstance(node, UnaryOpNode):
        return f"UnaryOp({node.op})"
    if isinstance(node, BinaryOpNode):
        return f"BinaryOp({node.op})"
    return str(node)


def tree_to_ascii(node: ASTNode, use_unicode: bool = True) -> str:
    """
    Renders the AST as an ASCII / Unicode branch diagram for terminal display.
    Automatically falls back to pure ASCII (+--, \--, |) if Unicode box-drawing
    characters are not supported by the current environment.

    Example (Unicode):
        BinaryOp(+)
        ├── Number(2)
        └── BinaryOp(*)
            ├── Number(3)
            └── Number(4)

    Example (ASCII):
        BinaryOp(+)
        +-- Number(2)
        \\-- BinaryOp(*)
            +-- Number(3)
            \\-- Number(4)
    """
    import sys
    # Verify stdout encoding capability
    if use_unicode:
        try:
            encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
            "├── └── │".encode(encoding)
        except (UnicodeEncodeError, LookupError):
            use_unicode = False

    branch = "├── " if use_unicode else "+-- "
    corner = "└── " if use_unicode else "\\-- "
    pipe = "│   " if use_unicode else "|   "
    space = "    "

    lines: List[str] = []

    def _build(curr: ASTNode, prefix: str = "", is_tail: bool = True, is_root: bool = False) -> None:
        if is_root:
            lines.append(_node_label(curr))
        else:
            connector = corner if is_tail else branch
            lines.append(f"{prefix}{connector}{_node_label(curr)}")

        # Prepare prefix for child nodes
        if is_root:
            child_prefix = ""
        else:
            child_prefix = prefix + (space if is_tail else pipe)

        # Determine children
        children: List[ASTNode] = []
        if isinstance(curr, BinaryOpNode):
            children = [curr.left, curr.right]
        elif isinstance(curr, UnaryOpNode):
            children = [curr.operand]

        for i, child in enumerate(children):
            _build(child, child_prefix, is_tail=(i == len(children) - 1), is_root=False)

    _build(node, is_root=True)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. Graphviz DOT Export & PNG Rendering
# ---------------------------------------------------------------------------

def export_to_dot(node: ASTNode, title: str = "Abstract Syntax Tree") -> str:
    """
    Generates a Graphviz DOT representation of the AST with distinct node
    styling for operators, variables, and constants.
    """
    lines = [
        'digraph AST {',
        f'    label="{title}";',
        '    labelloc="t";',
        '    fontsize=14;',
        '    fontname="Helvetica,Arial,sans-serif";',
        '    node [fontname="Helvetica,Arial,sans-serif", fontsize=11];',
        '    edge [fontname="Helvetica,Arial,sans-serif", fontsize=9];',
    ]

    counter = 0

    def _traverse(curr: ASTNode) -> int:
        nonlocal counter
        my_id = counter
        counter += 1

        if isinstance(curr, NumberNode):
            lines.append(
                f'    node_{my_id} [label="{curr.value}", shape=box, style="filled,rounded", fillcolor="#E8F5E9", color="#4CAF50"];'
            )
        elif isinstance(curr, VariableNode):
            lines.append(
                f'    node_{my_id} [label="{curr.name}", shape=box, style="filled,rounded", fillcolor="#FFF3E0", color="#FF9800"];'
            )
        elif isinstance(curr, UnaryOpNode):
            lines.append(
                f'    node_{my_id} [label="{curr.op} (unary)", shape=circle, style=filled, fillcolor="#EDE7F6", color="#673AB7"];'
            )
            child_id = _traverse(curr.operand)
            lines.append(f'    node_{my_id} -> node_{child_id};')
        elif isinstance(curr, BinaryOpNode):
            lines.append(
                f'    node_{my_id} [label="{curr.op}", shape=circle, style=filled, fillcolor="#E1F5FE", color="#03A9F4"];'
            )
            left_id = _traverse(curr.left)
            right_id = _traverse(curr.right)
            lines.append(f'    node_{my_id} -> node_{left_id} [label="L"];')
            lines.append(f'    node_{my_id} -> node_{right_id} [label="R"];')

        return my_id

    _traverse(node)
    lines.append('}')
    return "\n".join(lines)


def render_ast_graph(
    node: ASTNode,
    filepath_no_ext: str = "ast_graph",
    title: str = "Abstract Syntax Tree"
) -> Tuple[str, Optional[str]]:
    """
    Exports the AST to a Graphviz .dot file, and attempts to render it to a PNG image.

    Returns:
        Tuple[str, Optional[str]]: (path_to_dot_file, path_to_png_file_or_None)
    """
    dot_content = export_to_dot(node, title=title)
    dot_path = f"{filepath_no_ext}.dot"
    png_path = f"{filepath_no_ext}.png"

    with open(dot_path, "w", encoding="utf-8") as f:
        f.write(dot_content)

    # 1. Attempt using python 'graphviz' module if installed
    try:
        import graphviz  # type: ignore
        src = graphviz.Source(dot_content)
        # render outputs filepath_no_ext.png
        src.render(filepath_no_ext, format="png", cleanup=False)
        if os.path.exists(png_path):
            return dot_path, png_path
    except ImportError:
        pass
    except Exception:
        pass

    # 2. Attempt using system 'dot' executable if installed in PATH
    dot_cmd = shutil.which("dot")
    if dot_cmd:
        try:
            res = subprocess.run(
                [dot_cmd, "-Tpng", dot_path, "-o", png_path],
                capture_output=True,
                check=False
            )
            if res.returncode == 0 and os.path.exists(png_path):
                return dot_path, png_path
        except Exception:
            pass

    return dot_path, None


# ---------------------------------------------------------------------------
# 4. AST Evaluator (Tree-Walk Interpreter)
# ---------------------------------------------------------------------------

def collect_variables(node: ASTNode) -> Set[str]:
    """Scans the AST and returns the set of all variable names present."""
    vars_found: Set[str] = set()

    def _visit(curr: ASTNode) -> None:
        if isinstance(curr, VariableNode):
            vars_found.add(curr.name)
        elif isinstance(curr, UnaryOpNode):
            _visit(curr.operand)
        elif isinstance(curr, BinaryOpNode):
            _visit(curr.left)
            _visit(curr.right)

    _visit(node)
    return vars_found


def evaluate(
    node: ASTNode,
    variables: Optional[Dict[str, Union[int, float]]] = None
) -> Union[int, float]:
    """
    Recursively evaluates the AST using tree-walk interpretation.

    Args:
        node (ASTNode): The root of the AST.
        variables (dict, optional): Mapping from variable names to numeric values.

    Returns:
        Union[int, float]: The calculated numerical value.
    """
    if variables is None:
        variables = {}

    if isinstance(node, NumberNode):
        return node.value

    if isinstance(node, VariableNode):
        if node.name not in variables:
            known = list(variables.keys())
            raise EvaluationError(
                f"Undefined variable '{node.name}'. Defined variables: {known if known else 'None'}"
            )
        return variables[node.name]

    if isinstance(node, UnaryOpNode):
        operand_val = evaluate(node.operand, variables)
        if node.op == '-':
            return -operand_val
        elif node.op == '+':
            return +operand_val
        else:
            raise EvaluationError(f"Unsupported unary operator: '{node.op}'")

    if isinstance(node, BinaryOpNode):
        left_val = evaluate(node.left, variables)
        right_val = evaluate(node.right, variables)
        op = node.op

        if op == '+':
            res = left_val + right_val
        elif op == '-':
            res = left_val - right_val
        elif op == '*':
            res = left_val * right_val
        elif op == '/':
            if right_val == 0:
                raise EvaluationError("Division by zero")
            res = left_val / right_val
        elif op == '%':
            if right_val == 0:
                raise EvaluationError("Modulo by zero")
            res = left_val % right_val
        elif op == '^':
            try:
                res = left_val ** right_val
                if isinstance(res, complex):
                    raise EvaluationError(
                        f"Complex result from '{left_val} ^ {right_val}' (negative base with fractional exponent)"
                    )
            except OverflowError:
                raise EvaluationError(f"Arithmetic overflow in '{left_val} ^ {right_val}'")
        else:
            raise EvaluationError(f"Unsupported binary operator: '{op}'")

        # Normalize whole floats to integer (e.g., 4.0 -> 4) for cleaner output
        if isinstance(res, float) and res.is_integer():
            return int(res)
        return res

    raise EvaluationError(f"Unknown AST node type: {type(node)}")
