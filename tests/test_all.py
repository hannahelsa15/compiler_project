"""
test_all.py - Comprehensive Unit & Integration Test Suite.

Contains 35+ test cases covering:
  - Lexical analysis & tokenization (numbers, identifiers, operators, parens, positions)
  - Unary minus detection in all contexts vs binary minus
  - Precedence and associativity (left-associative -, /, right-associative ^)
  - Dijkstra's Shunting-Yard conversion & step-by-step trace generation
  - Error detection (unbalanced parens, double operators, empty input, malformed numbers)
  - Abstract Syntax Tree construction via Postfix stack
  - Abstract Syntax Tree construction via Infix Recursive Descent Parser
  - Structural AST equivalence between both parsing paradigms
  - Tree traversals (inorder parenthesized, preorder, postorder)
  - ASCII tree rendering & Graphviz DOT export
  - Evaluation of arithmetic expressions, variables, and runtime errors
"""

import os
import sys
import unittest

# Ensure parent directory is in Python path for direct test execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lexer import Lexer, LexerError, Token, TokenType, tokenize
from infix_to_postfix import (
    ShuntingYard,
    ShuntingYardError,
    format_trace_table,
    infix_to_postfix,
    postfix_to_string,
)
from ast_builder import (
    ASTBuildError,
    ASTNode,
    BinaryOpNode,
    NumberNode,
    UnaryOpNode,
    VariableNode,
    build_ast_from_infix,
    build_ast_from_postfix,
)
from tree_ops import (
    EvaluationError,
    collect_variables,
    evaluate,
    export_to_dot,
    inorder,
    postorder,
    postorder_str,
    preorder,
    preorder_str,
    tree_to_ascii,
)


class TestLexer(unittest.TestCase):
    """Tests for Phase 1: Lexical Analysis."""

    def test_numbers_integer_and_float(self):
        tokens = tokenize("42 3.14 .5")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        values = [t.value for t in tokens if t.type != TokenType.EOF]
        self.assertEqual(types, [TokenType.NUMBER, TokenType.NUMBER, TokenType.NUMBER])
        self.assertEqual(values, [42, 3.14, 0.5])

    def test_identifiers(self):
        tokens = tokenize("x alpha_1 _var")
        values = [t.value for t in tokens if t.type != TokenType.EOF]
        self.assertEqual(values, ["x", "alpha_1", "_var"])

    def test_all_operators(self):
        tokens = tokenize("a + b - c * d / e % f ^ g")
        ops = [t.value for t in tokens if t.type == TokenType.OPERATOR]
        self.assertEqual(ops, ["+", "-", "*", "/", "%", "^"])

    def test_parentheses(self):
        tokens = tokenize("( )")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        self.assertEqual(types, [TokenType.LPAREN, TokenType.RPAREN])

    def test_position_tracking(self):
        source = "2 +\n  34"
        tokens = tokenize(source)
        # Token '2' at line 1, col 1
        self.assertEqual((tokens[0].line, tokens[0].column), (1, 1))
        # Token '+' at line 1, col 3
        self.assertEqual((tokens[1].line, tokens[1].column), (1, 3))
        # Token '34' at line 2, col 3
        self.assertEqual((tokens[2].line, tokens[2].column), (2, 3))

    def test_unary_minus_at_start(self):
        tokens = tokenize("-3 + 4")
        self.assertEqual(tokens[0].type, TokenType.UNARY_MINUS)
        self.assertEqual(tokens[0].value, "u-")
        self.assertEqual(tokens[2].type, TokenType.OPERATOR)
        self.assertEqual(tokens[2].value, "+")

    def test_unary_minus_after_operator(self):
        tokens = tokenize("2 * -x")
        self.assertEqual(tokens[1].type, TokenType.OPERATOR)
        self.assertEqual(tokens[1].value, "*")
        self.assertEqual(tokens[2].type, TokenType.UNARY_MINUS)
        self.assertEqual(tokens[2].value, "u-")

    def test_unary_minus_after_lparen(self):
        tokens = tokenize("(-5)")
        self.assertEqual(tokens[0].type, TokenType.LPAREN)
        self.assertEqual(tokens[1].type, TokenType.UNARY_MINUS)
        self.assertEqual(tokens[1].value, "u-")

    def test_chained_unary_minuses(self):
        tokens = tokenize("--x")
        self.assertEqual(tokens[0].type, TokenType.UNARY_MINUS)
        self.assertEqual(tokens[1].type, TokenType.UNARY_MINUS)
        self.assertEqual(tokens[2].type, TokenType.IDENTIFIER)

    def test_binary_minus_distinction(self):
        tokens = tokenize("8 - 3")
        self.assertEqual(tokens[1].type, TokenType.OPERATOR)
        self.assertEqual(tokens[1].value, "-")

    def test_invalid_character_error(self):
        with self.assertRaises(LexerError) as ctx:
            tokenize("2 + $ * 3")
        self.assertIn("Invalid character '$'", str(ctx.exception))

    def test_multiple_decimal_points_error(self):
        with self.assertRaises(LexerError) as ctx:
            tokenize("3.14.15")
        self.assertIn("multiple decimal points", str(ctx.exception))


class TestShuntingYard(unittest.TestCase):
    """Tests for Phase 2: Shunting-Yard Infix to Postfix."""

    def test_operator_precedence_mult_over_add(self):
        tokens = tokenize("2 + 3 * 4")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "2 3 4 * +")

    def test_operator_precedence_power_over_mult(self):
        tokens = tokenize("2 * 3 ^ 2")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "2 3 2 ^ *")

    def test_left_associativity_subtraction(self):
        # 8 - 3 - 2 must be (8 - 3) - 2 -> "8 3 - 2 -"
        tokens = tokenize("8 - 3 - 2")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "8 3 - 2 -")

    def test_left_associativity_division(self):
        # 16 / 4 / 2 must be (16 / 4) / 2 -> "16 4 / 2 /"
        tokens = tokenize("16 / 4 / 2")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "16 4 / 2 /")

    def test_right_associativity_exponentiation(self):
        # 2 ^ 3 ^ 2 must be 2 ^ (3 ^ 2) -> "2 3 2 ^ ^"
        tokens = tokenize("2 ^ 3 ^ 2")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "2 3 2 ^ ^")

    def test_nested_parentheses(self):
        tokens = tokenize("((2 + 3) * (4 - 1))")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "2 3 + 4 1 - *")

    def test_unary_minus_postfix(self):
        tokens = tokenize("-3 + 4")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "3 u- 4 +")

    def test_unary_minus_with_multiplication(self):
        tokens = tokenize("2 * -x")
        post_tokens, _ = infix_to_postfix(tokens)
        self.assertEqual(postfix_to_string(post_tokens), "2 x u- *")

    def test_trace_table_generation(self):
        tokens = tokenize("2 + 3")
        post_tokens, trace = infix_to_postfix(tokens)
        self.assertTrue(len(trace) >= 3)
        formatted = format_trace_table(trace)
        self.assertIn("Token", formatted)
        self.assertIn("Operator Stack", formatted)
        self.assertIn("Postfix Output", formatted)

    def test_error_unbalanced_closing_paren(self):
        tokens = tokenize("2 + 3)")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("unexpected ')'", str(ctx.exception))

    def test_error_unbalanced_opening_paren(self):
        tokens = tokenize("(2 + 3")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("unclosed '('", str(ctx.exception))

    def test_error_consecutive_binary_operators(self):
        tokens = tokenize("2 + * 3")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("Consecutive operators", str(ctx.exception))

    def test_error_trailing_operator(self):
        tokens = tokenize("2 +")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("Unexpected end of expression after binary operator", str(ctx.exception))

    def test_error_trailing_unary_minus(self):
        tokens = tokenize("2 * -")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("Unexpected end of expression after unary operator", str(ctx.exception))

    def test_error_empty_expression(self):
        tokens = tokenize("   ")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("Empty expression", str(ctx.exception))

    def test_error_empty_parentheses(self):
        tokens = tokenize("()")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("Empty parentheses", str(ctx.exception))

    def test_error_missing_operator_between_operands(self):
        tokens = tokenize("2 3")
        with self.assertRaises(ShuntingYardError) as ctx:
            infix_to_postfix(tokens)
        self.assertIn("Missing operator", str(ctx.exception))


class TestASTBuilderAndEquivalence(unittest.TestCase):
    """Tests for Phase 3: AST Construction & Dual Parser Equivalence."""

    def test_build_ast_from_postfix_basic(self):
        tokens = tokenize("2 + 3")
        post_tokens, _ = infix_to_postfix(tokens)
        ast = build_ast_from_postfix(post_tokens)
        expected = BinaryOpNode("+", NumberNode(2), NumberNode(3))
        self.assertEqual(ast, expected)

    def test_build_ast_from_infix_basic(self):
        tokens = tokenize("2 + 3")
        ast = build_ast_from_infix(tokens)
        expected = BinaryOpNode("+", NumberNode(2), NumberNode(3))
        self.assertEqual(ast, expected)

    def test_dual_builder_equivalence_suite(self):
        """
        Critical Course Requirement: Verify that Postfix stack builder and
        Infix recursive descent parser yield identical ASTs across diverse expressions.
        """
        expressions = [
            "2 + 3",
            "2 + 3 * 4",
            "(8 - 3) * 2",
            "2 ^ 3 ^ 2",
            "8 - 3 - 2",
            "-3 + 4",
            "2 * -x",
            "-2 ^ 2",
            "-(2 ^ 2)",
            "2 ^ -3",
            "--x + 5",
            "((a + b) * (c - d)) / e ^ 2",
            "10 % 3 + 4 * 2"
        ]

        for expr in expressions:
            toks = tokenize(expr)
            post_toks, _ = infix_to_postfix(toks)
            ast_post = build_ast_from_postfix(post_toks)
            ast_infix = build_ast_from_infix(toks)
            self.assertEqual(
                ast_post,
                ast_infix,
                f"Mismatch for expression '{expr}': Postfix AST {ast_post!r} != Infix AST {ast_infix!r}"
            )


class TestTreeOperations(unittest.TestCase):
    """Tests for Phase 4: Traversals, ASCII Tree, and DOT Export."""

    def setUp(self):
        self.toks = tokenize("2 + 3 * 4")
        self.ast = build_ast_from_infix(self.toks)

    def test_inorder_fully_parenthesized(self):
        self.assertEqual(inorder(self.ast), "(2 + (3 * 4))")

    def test_inorder_parenthesized_associativity(self):
        ast_exp = build_ast_from_infix(tokenize("2 ^ 3 ^ 2"))
        self.assertEqual(inorder(ast_exp), "(2 ^ (3 ^ 2))")

        ast_sub = build_ast_from_infix(tokenize("8 - 3 - 2"))
        self.assertEqual(inorder(ast_sub), "((8 - 3) - 2)")

    def test_preorder_traversal(self):
        self.assertEqual(preorder_str(self.ast), "+ 2 * 3 4")

    def test_postorder_traversal(self):
        self.assertEqual(postorder_str(self.ast), "2 3 4 * +")

    def test_ascii_tree_rendering(self):
        ascii_rep = tree_to_ascii(self.ast)
        self.assertIn("BinaryOp(+)", ascii_rep)
        self.assertIn("Number(2)", ascii_rep)
        self.assertIn("BinaryOp(*)", ascii_rep)

    def test_export_to_dot(self):
        dot_str = export_to_dot(self.ast)
        self.assertTrue(dot_str.startswith("digraph AST {"))
        self.assertIn("node [", dot_str)
        self.assertIn('label="+"', dot_str)
        self.assertIn('label="*"', dot_str)
        self.assertTrue(dot_str.endswith("}"))

    def test_collect_variables(self):
        toks = tokenize("2 * x + y ^ z")
        ast = build_ast_from_infix(toks)
        self.assertEqual(collect_variables(ast), {"x", "y", "z"})


class TestEvaluation(unittest.TestCase):
    """Tests for Phase 4: Semantic Evaluation & Error Handling."""

    def test_arithmetic_precedence(self):
        ast = build_ast_from_infix(tokenize("2 + 3 * 4"))
        self.assertEqual(evaluate(ast), 14)

    def test_right_associativity_power(self):
        # 2 ^ (3 ^ 2) = 2 ^ 9 = 512
        ast = build_ast_from_infix(tokenize("2 ^ 3 ^ 2"))
        self.assertEqual(evaluate(ast), 512)

    def test_left_associativity_subtraction(self):
        # (8 - 3) - 2 = 5 - 2 = 3
        ast = build_ast_from_infix(tokenize("8 - 3 - 2"))
        self.assertEqual(evaluate(ast), 3)

    def test_unary_minus_evaluation(self):
        ast1 = build_ast_from_infix(tokenize("-3 + 4"))
        self.assertEqual(evaluate(ast1), 1)

        ast2 = build_ast_from_infix(tokenize("2 * -3"))
        self.assertEqual(evaluate(ast2), -6)

    def test_variables_evaluation(self):
        ast = build_ast_from_infix(tokenize("2 * x + y ^ 2"))
        result = evaluate(ast, {"x": 3, "y": 4})
        self.assertEqual(result, 22)  # 2 * 3 + 4^2 = 6 + 16 = 22

    def test_division_by_zero(self):
        ast = build_ast_from_infix(tokenize("10 / 0"))
        with self.assertRaises(EvaluationError) as ctx:
            evaluate(ast)
        self.assertIn("Division by zero", str(ctx.exception))

    def test_modulo_by_zero(self):
        ast = build_ast_from_infix(tokenize("10 % 0"))
        with self.assertRaises(EvaluationError) as ctx:
            evaluate(ast)
        self.assertIn("Modulo by zero", str(ctx.exception))

    def test_undefined_variable_error(self):
        ast = build_ast_from_infix(tokenize("x + 1"))
        with self.assertRaises(EvaluationError) as ctx:
            evaluate(ast, {"y": 2})
        self.assertIn("Undefined variable 'x'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
