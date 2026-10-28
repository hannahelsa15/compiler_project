"""
infix_to_postfix.py - Converts Infix Arithmetic Expressions to Postfix (RPN).

This module implements Phase 2 of the compiler pipeline:
using Dijkstra's Shunting-Yard algorithm to convert an infix token stream
into Reverse Polish Notation (Postfix).

Features:
- Full operator precedence:
    Level 4: Unary minus (u-) [Right-associative]
    Level 3: Exponentiation (^) [Right-associative]
    Level 2: Multiplication (*), Division (/), Modulo (%) [Left-associative]
    Level 1: Addition (+), Subtraction (-) [Left-associative]
- Parentheses handling and arbitrary nesting
- Syntax validation (detects unbalanced parentheses, consecutive operators, missing operands, etc.)
- Detailed step-by-step trace table generation (Token | Stack | Output)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from lexer import Token, TokenType, tokenize, LexerError


class ShuntingYardError(Exception):
    """Exception raised when an expression is malformed during Shunting-Yard conversion."""
    def __init__(self, message: str, token: Optional[Token] = None):
        self.message = message
        self.token = token
        if token:
            super().__init__(f"SyntaxError: {message} at line {token.line}, column {token.column}")
        else:
            super().__init__(f"SyntaxError: {message}")


@dataclass
class OperatorInfo:
    precedence: int
    associativity: str  # 'L' for left, 'R' for right


# Precedence and Associativity Table
OPERATOR_TABLE: Dict[str, OperatorInfo] = {
    'u-': OperatorInfo(precedence=4, associativity='R'),  # Unary minus
    'u+': OperatorInfo(precedence=4, associativity='R'),  # Unary plus
    '^':  OperatorInfo(precedence=3, associativity='R'),  # Exponentiation
    '*':  OperatorInfo(precedence=2, associativity='L'),  # Multiplication
    '/':  OperatorInfo(precedence=2, associativity='L'),  # Division
    '%':  OperatorInfo(precedence=2, associativity='L'),  # Modulo
    '+':  OperatorInfo(precedence=1, associativity='L'),  # Binary addition
    '-':  OperatorInfo(precedence=1, associativity='L'),  # Binary subtraction
}


@dataclass
class TraceStep:
    """Represents a single step in the Shunting-Yard execution trace."""
    token: str
    stack: str
    output: str


class ShuntingYard:
    """
    Implements Dijkstra's Shunting-Yard algorithm with syntax validation
    and step-by-step trace generation.
    """
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.operator_stack: List[Token] = []
        self.output_queue: List[Token] = []
        self.trace: List[TraceStep] = []

    def _record_trace(self, token_str: str) -> None:
        """Record current state for the trace table."""
        stack_str = "[" + " ".join(str(t.value) for t in self.operator_stack) + "]"
        output_str = " ".join(str(t.value) for t in self.output_queue)
        self.trace.append(TraceStep(token=token_str, stack=stack_str, output=output_str))

    def _validate_syntax(self) -> None:
        """
        Pre-validates the token stream to catch malformed expressions
        such as empty inputs, consecutive operators, missing operators, etc.
        """
        # Filter out EOF for validation
        substantive_tokens = [t for t in self.tokens if t.type != TokenType.EOF]

        if not substantive_tokens:
            raise ShuntingYardError("Empty expression")

        # Check for empty parentheses ()
        for i in range(len(substantive_tokens) - 1):
            if (substantive_tokens[i].type == TokenType.LPAREN and
                    substantive_tokens[i + 1].type == TokenType.RPAREN):
                raise ShuntingYardError("Empty parentheses '()'", substantive_tokens[i])

        # Validate token transitions
        prev: Optional[Token] = None
        for i, curr in enumerate(substantive_tokens):
            if prev is not None:
                # 1. Two consecutive binary operators: e.g. "2 + * 3"
                if prev.type == TokenType.OPERATOR and curr.type == TokenType.OPERATOR:
                    raise ShuntingYardError(
                        f"Consecutive operators: unexpected '{curr.value}' after '{prev.value}'",
                        curr
                    )

                # 2. Binary operator after opening parenthesis: e.g. "( * 3 )"
                if prev.type == TokenType.LPAREN and curr.type == TokenType.OPERATOR:
                    raise ShuntingYardError(
                        f"Unexpected binary operator '{curr.value}' immediately following '('",
                        curr
                    )

                # 3. Missing operator between operands or adjacent parens:
                # e.g. "2 3", "2 x", "(2) 3", "2 (3)", "(2)(3)"
                prev_is_operand = prev.type in (TokenType.NUMBER, TokenType.IDENTIFIER, TokenType.RPAREN)
                curr_is_operand = curr.type in (TokenType.NUMBER, TokenType.IDENTIFIER, TokenType.LPAREN)
                if prev_is_operand and curr_is_operand:
                    raise ShuntingYardError(
                        f"Missing operator between '{prev.value}' and '{curr.value}'",
                        curr
                    )

                # 4. Closing parenthesis immediately after an operator: e.g. "( 2 + )"
                if prev.type in (TokenType.OPERATOR, TokenType.UNARY_MINUS) and curr.type == TokenType.RPAREN:
                    raise ShuntingYardError(
                        f"Unexpected ')' immediately following operator '{prev.value}'",
                        curr
                    )

            prev = curr

        # Check trailing operator
        last = substantive_tokens[-1]
        if last.type == TokenType.OPERATOR:
            raise ShuntingYardError(
                f"Unexpected end of expression after binary operator '{last.value}'",
                last
            )
        if last.type == TokenType.UNARY_MINUS:
            raise ShuntingYardError(
                f"Unexpected end of expression after unary operator '{last.value}'",
                last
            )

    def parse(self) -> Tuple[List[Token], List[TraceStep]]:
        """
        Executes the Shunting-Yard algorithm.
        Returns:
            Tuple[List[Token], List[TraceStep]]: The postfix token list and the trace table.
        """
        self._validate_syntax()

        for token in self.tokens:
            if token.type == TokenType.EOF:
                break

            if token.type in (TokenType.NUMBER, TokenType.IDENTIFIER):
                # Operands are directly added to the output queue
                self.output_queue.append(token)
                self._record_trace(str(token.value))

            elif token.type in (TokenType.OPERATOR, TokenType.UNARY_MINUS):
                op_key = str(token.value)
                op_info = OPERATOR_TABLE[op_key]

                # Pop operators from the stack to the output while they have higher precedence,
                # or equal precedence if the incoming operator is left-associative.
                while self.operator_stack:
                    top_token = self.operator_stack[-1]
                    if top_token.type == TokenType.LPAREN:
                        break

                    top_info = OPERATOR_TABLE[str(top_token.value)]

                    should_pop = False
                    if op_info.associativity == 'L' and top_info.precedence >= op_info.precedence:
                        should_pop = True
                    elif op_info.associativity == 'R' and top_info.precedence > op_info.precedence:
                        should_pop = True

                    if should_pop:
                        self.output_queue.append(self.operator_stack.pop())
                    else:
                        break

                self.operator_stack.append(token)
                self._record_trace(str(token.value))

            elif token.type == TokenType.LPAREN:
                # Push left parenthesis onto the operator stack
                self.operator_stack.append(token)
                self._record_trace("(")

            elif token.type == TokenType.RPAREN:
                # Pop from operator stack to output until matching '(' is found
                found_lparen = False
                while self.operator_stack:
                    top = self.operator_stack.pop()
                    if top.type == TokenType.LPAREN:
                        found_lparen = True
                        break
                    self.output_queue.append(top)

                if not found_lparen:
                    raise ShuntingYardError("Mismatched parentheses: unexpected ')'", token)

                self._record_trace(")")

        # Pop any remaining operators on the stack to the output
        while self.operator_stack:
            top = self.operator_stack.pop()
            if top.type == TokenType.LPAREN:
                raise ShuntingYardError("Mismatched parentheses: unclosed '('", top)
            self.output_queue.append(top)

        self._record_trace("(end)")
        return self.output_queue, self.trace


def infix_to_postfix(tokens: List[Token]) -> Tuple[List[Token], List[TraceStep]]:
    """Helper function to run Shunting-Yard on a token list."""
    sy = ShuntingYard(tokens)
    return sy.parse()


def postfix_to_string(tokens: List[Token]) -> str:
    """Formats a list of postfix tokens into a space-separated string."""
    return " ".join(str(t.value) for t in tokens)


def format_trace_table(trace: List[TraceStep]) -> str:
    """
    Renders the Shunting-Yard trace steps as a clean ASCII formatted table.
    Columns dynamically adapt to content width.
    """
    if not trace:
        return "Trace table is empty."

    col_token_w = max(len("Token"), max((len(step.token) for step in trace), default=5)) + 2
    col_stack_w = max(len("Operator Stack"), max((len(step.stack) for step in trace), default=14)) + 2
    col_out_w = max(len("Postfix Output"), max((len(step.output) for step in trace), default=14)) + 2

    # Border lines
    sep_line = f"+{'-' * col_token_w}+{'-' * col_stack_w}+{'-' * col_out_w}+"
    header = (
        f"| {'Token':<{col_token_w - 2}} "
        f"| {'Operator Stack':<{col_stack_w - 2}} "
        f"| {'Postfix Output':<{col_out_w - 2}} |"
    )

    rows = [sep_line, header, sep_line]
    for step in trace:
        row = (
            f"| {step.token:<{col_token_w - 2}} "
            f"| {step.stack:<{col_stack_w - 2}} "
            f"| {step.output:<{col_out_w - 2}} |"
        )
        rows.append(row)
    rows.append(sep_line)

    return "\n".join(rows)
