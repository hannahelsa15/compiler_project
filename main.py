"""
main.py - Interactive CLI & Command-Line Driver for Infix-to-Postfix & AST Compiler.

Features:
  - Command-line mode: pass expression directly via sys.argv or flags
  - Interactive REPL mode with session variable memory and command shortcuts
  - Full display of all compiler stages:
      1. Source Expression
      2. Lexer Tokens
      3. Shunting-Yard Trace Table
      4. Postfix (RPN) Output
      5. Dual AST Construction & Equivalence Verification
      6. Terminal ASCII Tree Visualization
      7. Tree Traversals (Inorder parenthesized, Preorder, Postorder)
      8. Evaluation (with variable substitution)
      9. Graphviz DOT export and optional PNG generation
"""

import argparse
import os
import sys
from typing import Dict, Optional, Union

# Attempt to configure UTF-8 output if possible
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from lexer import LexerError, tokenize
from infix_to_postfix import (
    ShuntingYardError,
    format_trace_table,
    infix_to_postfix,
    postfix_to_string,
)
from ast_builder import (
    ASTBuildError,
    build_ast_from_infix,
    build_ast_from_postfix,
)
from tree_ops import (
    EvaluationError,
    collect_variables,
    evaluate,
    inorder,
    postorder_str,
    preorder_str,
    render_ast_graph,
    tree_to_ascii,
)


def parse_vars_string(vars_str: str) -> Dict[str, Union[int, float]]:
    """
    Parses a string of comma-separated variable assignments,
    e.g. 'x=5, y=3.14, a=-2'.
    """
    variables: Dict[str, Union[int, float]] = {}
    if not vars_str or not vars_str.strip():
        return variables

    parts = vars_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '=' not in part:
            raise ValueError(f"Invalid variable assignment: '{part}'. Expected format 'var=value'")
        key, val_str = part.split('=', 1)
        key = key.strip()
        val_str = val_str.strip()
        try:
            val: Union[int, float] = float(val_str) if '.' in val_str else int(val_str)
        except ValueError:
            raise ValueError(f"Invalid numeric value '{val_str}' for variable '{key}'")
        variables[key] = val
    return variables


def process_expression(
    expr: str,
    variables: Optional[Dict[str, Union[int, float]]] = None,
    dot_output: Optional[str] = "ast_output",
    interactive: bool = False
) -> None:
    """
    Processes a single expression through all compiler phases and displays
    detailed step-by-step results.
    """
    if variables is None:
        variables = {}

    divider = "=" * 70
    section_div = "-" * 70

    print(divider)
    print(f" [1] INPUT EXPRESSION:  {expr}")
    print(divider)

    # -------------------------------------------------------------
    # Phase 1: Lexical Analysis
    # -------------------------------------------------------------
    try:
        tokens = tokenize(expr)
    except LexerError as e:
        print("\n[LEXER ERROR]")
        print(e)
        return

    # Filter EOF for cleaner display of tokens
    display_tokens = [t for t in tokens if t.type.name != 'EOF']
    token_str = ", ".join(f"{t.type.name}({t.value})" for t in display_tokens)
    print(f"\n[2] LEXICAL TOKENS ({len(display_tokens)} tokens):")
    print(f"    {token_str}")

    # -------------------------------------------------------------
    # Phase 2: Infix to Postfix (Shunting-Yard)
    # -------------------------------------------------------------
    try:
        postfix_tokens, trace = infix_to_postfix(tokens)
    except ShuntingYardError as e:
        print("\n[SHUNTING-YARD ERROR]")
        print(e)
        return

    print("\n[3] SHUNTING-YARD STEP-BY-STEP TRACE:")
    print(format_trace_table(trace))

    postfix_str = postfix_to_string(postfix_tokens)
    print(f"\n[4] POSTFIX EXPRESSION (RPN):")
    print(f"    {postfix_str}")

    # -------------------------------------------------------------
    # Phase 3: AST Construction & Dual Verification
    # -------------------------------------------------------------
    try:
        # Build 1: From Postfix using Stack
        ast_from_post = build_ast_from_postfix(postfix_tokens)
        # Build 2: From Infix using Recursive Descent Parser
        ast_from_inf = build_ast_from_infix(tokens)
        is_equivalent = (ast_from_post == ast_from_inf)
    except ASTBuildError as e:
        print("\n[AST CONSTRUCTION ERROR]")
        print(e)
        return

    print("\n[5] AST CONSTRUCTION & DUAL PARSER VERIFICATION:")
    print(f"    Stack-based AST (from Postfix):     {repr(ast_from_post)}")
    print(f"    Recursive Descent AST (from Infix): {repr(ast_from_inf)}")
    eq_status = "[MATCH] Identical Trees" if is_equivalent else "[MISMATCH] Trees Differ"
    print(f"    Verification Result:                {eq_status}")

    # -------------------------------------------------------------
    # Phase 4: AST ASCII Visualization
    # -------------------------------------------------------------
    print("\n[6] ABSTRACT SYNTAX TREE (ASCII HIERARCHY):")
    ascii_tree = tree_to_ascii(ast_from_post)
    for line in ascii_tree.splitlines():
        print(f"    {line}")

    # -------------------------------------------------------------
    # Phase 5: Tree Traversals
    # -------------------------------------------------------------
    inord = inorder(ast_from_post)
    preord = preorder_str(ast_from_post)
    postord = postorder_str(ast_from_post)

    print("\n[7] TREE TRAVERSALS:")
    print(f"    Inorder (Fully Parenthesized):  {inord}")
    print(f"    Preorder (Prefix / Polish):     {preord}")
    print(f"    Postorder (Postfix / RPN):      {postord}")

    # -------------------------------------------------------------
    # Phase 6: AST Evaluation
    # -------------------------------------------------------------
    needed_vars = collect_variables(ast_from_post)
    eval_vars = dict(variables)

    if interactive and needed_vars:
        missing_vars = needed_vars - set(eval_vars.keys())
        if missing_vars:
            print(f"\n[INPUT REQUIRED] Expression contains variables: {sorted(needed_vars)}")
            for var in sorted(missing_vars):
                while True:
                    try:
                        val_str = input(f"    Enter value for '{var}': ").strip()
                        val_num = float(val_str) if '.' in val_str else int(val_str)
                        eval_vars[var] = val_num
                        break
                    except ValueError:
                        print("    Invalid number, please try again.")

    print("\n[8] EVALUATION RESULT:")
    if needed_vars:
        vars_disp = ", ".join(f"{k}={v}" for k, v in eval_vars.items() if k in needed_vars)
        print(f"    Environment:   {{{vars_disp}}}")
    try:
        result = evaluate(ast_from_post, eval_vars)
        print(f"    Evaluated:     {result}")
    except EvaluationError as e:
        print(f"    Evaluation Error: {e}")

    # -------------------------------------------------------------
    # Phase 7: Graphviz Export & PNG
    # -------------------------------------------------------------
    if dot_output:
        dot_file, png_file = render_ast_graph(ast_from_post, dot_output, title=f"AST for: {expr}")
        print("\n[9] VISUALIZATION EXPORT:")
        print(f"    Graphviz DOT:  {os.path.abspath(dot_file)}")
        if png_file:
            print(f"    Rendered PNG:  {os.path.abspath(png_file)}")
        else:
            print("    PNG Rendering: Graphviz 'dot' not found in PATH or 'graphviz' Python module not installed.")
            print(f"                   To render PNG manually: dot -Tpng {dot_file} -o {dot_output}.png")

    print(divider)


def interactive_repl() -> None:
    """Runs the interactive command-line Read-Eval-Print Loop."""
    session_vars: Dict[str, Union[int, float]] = {}

    header = """
======================================================================
  INFIX TO POSTFIX CONVERTER & AST BUILDER (Compiler Construction)
======================================================================
Enter any arithmetic expression to trace lexical, syntactic, and
AST compiler phases.

Special Commands:
  :vars               Display current session variables
  :vars x=5, y=10     Set session variables
  :clear              Clear session variables / screen
  :help               Show this help message
  :exit, :quit        Exit the application
======================================================================
"""
    print(header)

    while True:
        try:
            line = input("compiler> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting. Goodbye!")
            break

        if not line:
            continue

        if line in (":exit", ":quit", "exit", "quit"):
            print("Exiting. Goodbye!")
            break

        if line == ":help":
            print(header)
            continue

        if line.startswith(":vars"):
            arg = line[len(":vars"):].strip()
            if not arg:
                print(f"Current session variables: {session_vars if session_vars else 'None'}")
            else:
                try:
                    new_vars = parse_vars_string(arg)
                    session_vars.update(new_vars)
                    print(f"Updated session variables: {session_vars}")
                except ValueError as e:
                    print(f"Error: {e}")
            continue

        if line == ":clear":
            session_vars.clear()
            print("Session variables cleared.")
            continue

        # Process the expression
        process_expression(
            line,
            variables=session_vars,
            dot_output="ast_output",
            interactive=True
        )


def main() -> None:
    """CLI entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Infix to Postfix Converter & AST Builder (Compiler Construction Mini-Project)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python main.py "2 + 3 * 4"
  python main.py "2 ^ 3 ^ 2"
  python main.py "2 * x + y ^ 2" --vars "x=3, y=4"
  python main.py "(8 - 3) * -2" --dot my_ast
  python main.py                (Enters interactive REPL mode)
"""
    )

    parser.add_argument(
        "expression",
        nargs="?",
        default=None,
        help="Infix arithmetic expression to analyze and evaluate (e.g., '2 + 3 * 4')"
    )

    parser.add_argument(
        "-v", "--vars",
        dest="variables",
        default="",
        help="Comma-separated variable definitions, e.g., 'x=5, y=3.14'"
    )

    parser.add_argument(
        "--dot",
        dest="dot_output",
        default="ast_output",
        help="Base filename for Graphviz DOT and PNG output (default: 'ast_output')"
    )

    parser.add_argument(
        "--no-dot",
        action="store_true",
        help="Disable Graphviz DOT generation"
    )

    args = parser.parse_args()

    if args.expression is None:
        # Interactive REPL mode
        interactive_repl()
    else:
        # Single expression mode
        try:
            vars_dict = parse_vars_string(args.variables)
        except ValueError as e:
            print(f"Argument Error: {e}", file=sys.stderr)
            sys.exit(1)

        dot_dest = None if args.no_dot else args.dot_output
        process_expression(
            args.expression,
            variables=vars_dict,
            dot_output=dot_dest,
            interactive=False
        )


if __name__ == "__main__":
    main()
