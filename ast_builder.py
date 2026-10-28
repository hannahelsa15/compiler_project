"""
ast_builder.py - Abstract Syntax Tree (AST) Construction.

This module implements Phase 3 of the compiler pipeline:
building an Abstract Syntax Tree (Intermediate Representation) using two
distinct parsing paradigms:
  1. Bottom-up stack-based AST construction from Postfix (RPN).
  2. Top-down Recursive Descent Parsing directly from Infix tokens.

Both approaches construct structurally identical ASTs, demonstrating the
theoretical equivalence of precedence-climbing / LL(1) recursive descent
and Dijkstra's operator-precedence / LR-style shunting-yard.

Node Classes:
  - ASTNode (Abstract Base)
  - NumberNode
  - VariableNode
  - BinaryOpNode
  - UnaryOpNode
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Union
from lexer import Token, TokenType, tokenize


class ASTBuildError(Exception):
    """Exception raised when an AST cannot be constructed due to malformed input."""
    pass


# ---------------------------------------------------------------------------
# AST Node Hierarchy
# ---------------------------------------------------------------------------

class ASTNode(ABC):
    """Abstract Base Class for all AST nodes."""

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        """Structural equality comparison between two ASTs."""
        pass

    @abstractmethod
    def __hash__(self) -> int:
        pass


class NumberNode(ASTNode):
    """
    Leaf node representing a numeric literal (int or float).
    """
    def __init__(self, value: Union[int, float]):
        self.value = value

    def __repr__(self) -> str:
        return f"NumberNode({self.value})"

    def __str__(self) -> str:
        return str(self.value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NumberNode) and self.value == other.value

    def __hash__(self) -> int:
        return hash(("NumberNode", self.value))


class VariableNode(ASTNode):
    """
    Leaf node representing an identifier (variable name).
    """
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f"VariableNode({self.name!r})"

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, VariableNode) and self.name == other.name

    def __hash__(self) -> int:
        return hash(("VariableNode", self.name))


class UnaryOpNode(ASTNode):
    """
    Interior node representing a unary operation (e.g. negation '-').
    """
    def __init__(self, op: str, operand: ASTNode):
        # Normalize operator symbol to '-' or '+'
        self.op = op.replace("u", "")
        self.operand = operand

    def __repr__(self) -> str:
        return f"UnaryOpNode({self.op!r}, {self.operand!r})"

    def __str__(self) -> str:
        return f"({self.op}{self.operand})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, UnaryOpNode) and
            self.op == other.op and
            self.operand == other.operand
        )

    def __hash__(self) -> int:
        return hash(("UnaryOpNode", self.op, self.operand))


class BinaryOpNode(ASTNode):
    """
    Interior node representing a binary operation (+, -, *, /, %, ^).
    """
    def __init__(self, op: str, left: ASTNode, right: ASTNode):
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"BinaryOpNode({self.op!r}, {self.left!r}, {self.right!r})"

    def __str__(self) -> str:
        return f"({self.left} {self.op} {self.right})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, BinaryOpNode) and
            self.op == other.op and
            self.left == other.left and
            self.right == other.right
        )

    def __hash__(self) -> int:
        return hash(("BinaryOpNode", self.op, self.left, self.right))


# ---------------------------------------------------------------------------
# 1. Postfix Stack-Based AST Builder
# ---------------------------------------------------------------------------

def build_ast_from_postfix(postfix_tokens: List[Token]) -> ASTNode:
    """
    Constructs an AST from a list of tokens in postfix notation (RPN)
    using an evaluation operand stack.

    Algorithm:
      1. For each token:
         - If operand (Number/Variable): push corresponding leaf node to stack.
         - If unary operator (u-, u+): pop 1 node, push UnaryOpNode.
         - If binary operator: pop right node, pop left node, push BinaryOpNode.
      2. At the end, exactly one node must remain on stack (the root).

    Time Complexity: O(N) where N is number of tokens.
    Space Complexity: O(N) for the operand stack.
    """
    if not postfix_tokens:
        raise ASTBuildError("Cannot construct AST from empty postfix token list")

    stack: List[ASTNode] = []

    for token in postfix_tokens:
        if token.type == TokenType.NUMBER:
            stack.append(NumberNode(token.value))
        elif token.type == TokenType.IDENTIFIER:
            stack.append(VariableNode(str(token.value)))
        elif token.type in (TokenType.UNARY_MINUS, TokenType.OPERATOR) and str(token.value) in ('u-', 'u+'):
            if not stack:
                raise ASTBuildError(f"Insufficient operands for unary operator '{token.value}'")
            operand = stack.pop()
            stack.append(UnaryOpNode(str(token.value), operand))
        elif token.type == TokenType.OPERATOR:
            if len(stack) < 2:
                raise ASTBuildError(
                    f"Insufficient operands for binary operator '{token.value}'"
                )
            right = stack.pop()
            left = stack.pop()
            stack.append(BinaryOpNode(str(token.value), left, right))
        else:
            raise ASTBuildError(f"Unexpected token type in postfix stream: {token}")

    if len(stack) != 1:
        raise ASTBuildError(
            f"Malformed postfix expression: expected 1 root node, but found {len(stack)} on stack"
        )

    return stack[0]


# ---------------------------------------------------------------------------
# 2. Infix Recursive Descent Parser AST Builder
# ---------------------------------------------------------------------------

class RecursiveDescentParser:
    """
    Constructs an AST directly from infix tokens using top-down recursive descent.

    Context-Free Grammar:
      expression -> term ( ('+' | '-') term )*
      term       -> power ( ('*' | '/' | '%') power )*
      power      -> unary ( '^' power )?             # Right-associative power
      unary      -> ('-' | '+') unary | primary       # Right-recursive unary
      primary    -> NUMBER | IDENTIFIER | '(' expression ')'
    """
    def __init__(self, tokens: List[Token]):
        # Filter out EOF for parsing convenience
        self.tokens = [t for t in tokens if t.type != TokenType.EOF]
        self.pos = 0

    def _peek(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _advance(self) -> Token:
        tok = self._peek()
        if tok is None:
            raise ASTBuildError("Unexpected end of input while parsing expression")
        self.pos += 1
        return tok

    def _match(self, *types_or_values: Any) -> Optional[Token]:
        tok = self._peek()
        if tok is None:
            return None
        for item in types_or_values:
            if isinstance(item, TokenType) and tok.type == item:
                return self._advance()
            if isinstance(item, str) and str(tok.value) == item:
                return self._advance()
        return None

    def parse(self) -> ASTNode:
        if not self.tokens:
            raise ASTBuildError("Cannot parse empty expression")
        ast = self._expression()
        if self.pos < len(self.tokens):
            extra_tok = self.tokens[self.pos]
            raise ASTBuildError(
                f"Unexpected token '{extra_tok.value}' at line {extra_tok.line}, column {extra_tok.column}"
            )
        return ast

    def _expression(self) -> ASTNode:
        """expression -> term ( ('+' | '-') term )*"""
        node = self._term()
        while True:
            tok = self._peek()
            if tok and tok.type == TokenType.OPERATOR and tok.value in ('+', '-'):
                op_token = self._advance()
                right = self._term()
                node = BinaryOpNode(str(op_token.value), node, right)
            else:
                break
        return node

    def _term(self) -> ASTNode:
        """term -> power ( ('*' | '/' | '%') power )*"""
        node = self._power()
        while True:
            tok = self._peek()
            if tok and tok.type == TokenType.OPERATOR and tok.value in ('*', '/', '%'):
                op_token = self._advance()
                right = self._power()
                node = BinaryOpNode(str(op_token.value), node, right)
            else:
                break
        return node

    def _power(self) -> ASTNode:
        """power -> unary ( '^' power )?   (Right-associative)"""
        node = self._unary()
        tok = self._peek()
        if tok and tok.type == TokenType.OPERATOR and tok.value == '^':
            self._advance()
            # Recursive call to _power() enforces right-associativity: 2 ^ (3 ^ 2)
            right = self._power()
            return BinaryOpNode('^', node, right)
        return node

    def _unary(self) -> ASTNode:
        """unary -> ('-' | '+') unary | primary"""
        tok = self._peek()
        if tok:
            if tok.type == TokenType.UNARY_MINUS or (tok.type == TokenType.OPERATOR and tok.value == '-'):
                self._advance()
                operand = self._unary()
                return UnaryOpNode('-', operand)
            elif (tok.type == TokenType.OPERATOR and tok.value == '+') or (str(tok.value) == 'u+'):
                self._advance()
                operand = self._unary()
                return UnaryOpNode('+', operand)

        return self._primary()

    def _primary(self) -> ASTNode:
        """primary -> NUMBER | IDENTIFIER | '(' expression ')'"""
        tok = self._peek()
        if tok is None:
            raise ASTBuildError("Expected number, variable, or '(' but reached end of input")

        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberNode(tok.value)

        if tok.type == TokenType.IDENTIFIER:
            self._advance()
            return VariableNode(str(tok.value))

        if tok.type == TokenType.LPAREN:
            self._advance()
            node = self._expression()
            closing = self._peek()
            if closing is None or closing.type != TokenType.RPAREN:
                col = tok.column
                raise ASTBuildError(f"Mismatched parentheses: missing ')' for '(' opened at column {col}")
            self._advance()  # Consume ')'
            return node

        raise ASTBuildError(
            f"Unexpected token '{tok.value}' (type {tok.type.name}) at line {tok.line}, column {tok.column}"
        )


def build_ast_from_infix(tokens: List[Token]) -> ASTNode:
    """Helper function to build an AST directly from infix tokens via recursive descent."""
    parser = RecursiveDescentParser(tokens)
    return parser.parse()
