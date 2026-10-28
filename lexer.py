"""
lexer.py - Lexical Analysis (Scanner) for Arithmetic Expressions.

This module is responsible for Phase 1 of the compiler pipeline:
scanning raw source text and converting it into a structured stream of tokens.

Features:
- Tokenizes: NUMBER (int/float), IDENTIFIER, OPERATOR (+ - * / % ^), LPAREN, RPAREN, EOF
- Precise position tracking (line number, column number, character offset)
- Context-aware detection of unary minus vs binary minus
- Informative compiler error messages with visual source-code pointers
"""

from enum import Enum, auto
from typing import Any, List, Optional, Union


class TokenType(Enum):
    """Enumeration of lexical token types recognized by the compiler."""
    NUMBER = auto()       # Integer or floating-point literal (e.g. 42, 3.14, .5)
    IDENTIFIER = auto()   # Variable name (e.g. x, alpha, var_1)
    OPERATOR = auto()     # Binary operator (+, -, *, /, %, ^)
    UNARY_MINUS = auto()  # Unary negation operator (distinguished from binary -)
    LPAREN = auto()       # '('
    RPAREN = auto()       # ')'
    EOF = auto()          # End of input stream


class Token:
    """
    Represents a lexical token with its type, value, and source location.

    Attributes:
        type (TokenType): The token classification.
        value (Any): The semantic value (e.g., int/float for NUMBER, str for OPERATOR/IDENTIFIER).
        line (int): 1-based source line number.
        column (int): 1-based source column number.
        position (int): 0-based character index in the full source text.
    """
    def __init__(self, type_: TokenType, value: Any, line: int, column: int, position: int = 0):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column
        self.position = position

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.column})"

    def __str__(self) -> str:
        return str(self.value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Token):
            return False
        return (
            self.type == other.type and
            self.value == other.value and
            self.line == other.line and
            self.column == other.column
        )


class LexerError(Exception):
    """
    Exception raised when lexical scanning encounters an invalid character or token.
    Provides formatted diagnostic messages with visual caret pointers.
    """
    def __init__(self, message: str, line: int, column: int, source_code: str = ""):
        self.message = message
        self.line = line
        self.column = column
        self.source_code = source_code
        super().__init__(self.format_error())

    def format_error(self) -> str:
        header = f"LexerError: {self.message} at line {self.line}, column {self.column}"
        if not self.source_code:
            return header
        lines = self.source_code.splitlines()
        if 1 <= self.line <= len(lines):
            line_content = lines[self.line - 1]
            pointer = " " * (self.column - 1) + "^"
            return f"{header}\n    {line_content}\n    {pointer}"
        return header


class Lexer:
    """
    Lexical Analyzer (Scanner).
    
    Converts raw expression string into a list of Token objects.
    """
    VALID_OPERATORS = {'+', '-', '*', '/', '%', '^'}

    def __init__(self, source: str):
        self.source = source
        self.length = len(source)
        self.pos = 0        # Current index in source
        self.line = 1       # Current 1-based line
        self.column = 1     # Current 1-based column

    def peek(self) -> Optional[str]:
        """Look at the current character without advancing."""
        if self.pos >= self.length:
            return None
        return self.source[self.pos]

    def peek_next(self) -> Optional[str]:
        """Look at the character after current without advancing."""
        if self.pos + 1 >= self.length:
            return None
        return self.source[self.pos + 1]

    def advance(self) -> Optional[str]:
        """Consume and return the current character, advancing pointers."""
        if self.pos >= self.length:
            return None
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _number(self, start_line: int, start_col: int, start_pos: int) -> Token:
        """Scan an integer or floating-point number literal."""
        num_str = ""
        has_dot = False

        # Support numbers starting with a decimal point, e.g. .5
        if self.peek() == '.':
            has_dot = True
            num_str += self.advance()

        while True:
            ch = self.peek()
            if ch is not None and ch.isdigit():
                num_str += self.advance()
            elif ch == '.':
                if has_dot:
                    # Encountered a second decimal point in the same number
                    self.advance()
                    raise LexerError(
                        f"Malformed number literal: multiple decimal points in '{num_str}.'",
                        self.line,
                        self.column - 1,
                        self.source
                    )
                has_dot = True
                num_str += self.advance()
            else:
                break

        # A lone '.' is not a valid number
        if num_str == '.':
            raise LexerError("Unexpected character '.'", start_line, start_col, self.source)

        val: Union[int, float] = float(num_str) if has_dot else int(num_str)
        return Token(TokenType.NUMBER, val, start_line, start_col, start_pos)

    def _identifier(self, start_line: int, start_col: int, start_pos: int) -> Token:
        """Scan an identifier (variable name), e.g. x, var_1, alpha."""
        name = ""
        while True:
            ch = self.peek()
            if ch is not None and (ch.isalnum() or ch == '_'):
                name += self.advance()
            else:
                break
        return Token(TokenType.IDENTIFIER, name, start_line, start_col, start_pos)

    def tokenize(self) -> List[Token]:
        """
        Scan the entire source text and return the complete list of tokens,
        ending with an EOF token.
        """
        tokens: List[Token] = []

        while self.pos < self.length:
            ch = self.peek()

            # Skip whitespace
            if ch in (' ', '\t', '\r', '\n'):
                self.advance()
                continue

            start_line = self.line
            start_col = self.column
            start_pos = self.pos

            # Number literal (digits or . followed by digit)
            if ch.isdigit() or (ch == '.' and self.peek_next() is not None and self.peek_next().isdigit()):
                tokens.append(self._number(start_line, start_col, start_pos))
                continue

            # Identifier (starts with letter or underscore)
            if ch.isalpha() or ch == '_':
                tokens.append(self._identifier(start_line, start_col, start_pos))
                continue

            # Parentheses
            if ch == '(':
                self.advance()
                tokens.append(Token(TokenType.LPAREN, '(', start_line, start_col, start_pos))
                continue

            if ch == ')':
                self.advance()
                tokens.append(Token(TokenType.RPAREN, ')', start_line, start_col, start_pos))
                continue

            # Operator detection (including Unary Minus distinction)
            if ch in self.VALID_OPERATORS:
                self.advance()
                if ch == '-':
                    # Check context to distinguish unary minus from binary subtraction:
                    # A '-' is unary if:
                    # 1. It is the first token in the expression, OR
                    # 2. It immediately follows another binary operator, unary minus, or '('
                    last_tok = tokens[-1] if tokens else None
                    if last_tok is None or last_tok.type in (
                        TokenType.OPERATOR,
                        TokenType.UNARY_MINUS,
                        TokenType.LPAREN,
                    ):
                        tokens.append(Token(TokenType.UNARY_MINUS, 'u-', start_line, start_col, start_pos))
                    else:
                        tokens.append(Token(TokenType.OPERATOR, '-', start_line, start_col, start_pos))
                elif ch == '+':
                    # Handle unary plus similarly (normalize or treat as unary plus)
                    last_tok = tokens[-1] if tokens else None
                    if last_tok is None or last_tok.type in (
                        TokenType.OPERATOR,
                        TokenType.UNARY_MINUS,
                        TokenType.LPAREN,
                    ):
                        # Unary plus has no effect on numeric value; we can treat it as unary plus
                        # or skip/ignore it. To be consistent with unary minus, we record it as binary operator '+'
                        # if binary, or if unary we can also record or collapse.
                        # However, course requirement specifically asks for unary minus.
                        # For unary plus, we can keep it as OPERATOR or handle gracefully.
                        tokens.append(Token(TokenType.OPERATOR, '+', start_line, start_col, start_pos))
                    else:
                        tokens.append(Token(TokenType.OPERATOR, '+', start_line, start_col, start_pos))
                else:
                    tokens.append(Token(TokenType.OPERATOR, ch, start_line, start_col, start_pos))
                continue

            # Unrecognized character -> lexical error
            invalid_ch = self.advance()
            raise LexerError(
                f"Invalid character '{invalid_ch}'",
                start_line,
                start_col,
                self.source
            )

        tokens.append(Token(TokenType.EOF, '', self.line, self.column, self.pos))
        return tokens


def tokenize(source: str) -> List[Token]:
    """Helper convenience function to tokenize a source string."""
    lexer = Lexer(source)
    return lexer.tokenize()
