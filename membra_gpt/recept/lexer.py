"""RECEPT Lexer — tokenizes .recept source files."""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TokenType(Enum):
    # Keywords
    CAPSULE = auto()
    OBSERVE = auto()
    DECIDE = auto()
    EXECUTE = auto()
    ENDPOINT = auto()
    WORKFLOW = auto()
    STEP = auto()
    FN = auto()
    RETURN = auto()
    IF = auto()
    ELSE = auto()
    ELIF = auto()
    TRUE = auto()
    FALSE = auto()
    NONE = auto()
    RECEIPT = auto()
    AND = auto()
    OR = auto()
    NOT = auto()

    # HTTP methods
    GET = auto()
    POST = auto()
    PUT = auto()
    DELETE = auto()

    # Types
    TYPE_TEXT = auto()
    TYPE_INT = auto()
    TYPE_BOOL = auto()
    TYPE_ARTIFACT = auto()
    TYPE_RECEIPT = auto()
    TYPE_ENDPOINT = auto()
    TYPE_NONE = auto()

    # Annotations
    AT_APPROVED = auto()

    # Operators
    ASSIGN = auto()       # =
    ARROW = auto()        # ->
    EQ = auto()           # ==
    NEQ = auto()          # !=
    LT = auto()           # <
    GT = auto()           # >
    LTE = auto()          # <=
    GTE = auto()          # >=
    PLUS = auto()         # +
    MINUS = auto()        # -
    STAR = auto()         # *
    SLASH = auto()        # /
    DOT = auto()          # .
    COLON = auto()        # :
    COMMA = auto()        # ,
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    LBRACE = auto()       # {
    RBRACE = auto()       # }

    # Literals
    IDENT = auto()
    STRING = auto()
    NUMBER = auto()
    PATH = auto()         # /path/to/something

    # Structure
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"


KEYWORDS = {
    'capsule': TokenType.CAPSULE,
    'observe': TokenType.OBSERVE,
    'decide': TokenType.DECIDE,
    'execute': TokenType.EXECUTE,
    'endpoint': TokenType.ENDPOINT,
    'workflow': TokenType.WORKFLOW,
    'step': TokenType.STEP,
    'fn': TokenType.FN,
    'return': TokenType.RETURN,
    'if': TokenType.IF,
    'else': TokenType.ELSE,
    'elif': TokenType.ELIF,
    'true': TokenType.TRUE,
    'false': TokenType.FALSE,
    'none': TokenType.NONE,
    'receipt': TokenType.RECEIPT,
    'and': TokenType.AND,
    'or': TokenType.OR,
    'not': TokenType.NOT,
    'GET': TokenType.GET,
    'POST': TokenType.POST,
    'PUT': TokenType.PUT,
    'DELETE': TokenType.DELETE,
}


class Lexer:
    """Tokenizes RECEPT source code into a stream of tokens."""

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []
        self.indent_stack = [0]

    def error(self, msg: str):
        raise SyntaxError(f"RECEPT Lexer Error at line {self.line}, col {self.col}: {msg}")

    def peek(self, offset=0) -> str:
        pos = self.pos + offset
        if pos < len(self.source):
            return self.source[pos]
        return '\0'

    def advance(self) -> str:
        ch = self.peek()
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def skip_whitespace_inline(self):
        while self.peek() in (' ', '\t'):
            self.advance()

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.source):
            ch = self.peek()

            # Skip inline whitespace (spaces/tabs within a line)
            if ch in (' ', '\t'):
                self.advance()
                continue

            # Handle comments (#)
            if ch == '#':
                while self.peek() and self.peek() != '\n':
                    self.advance()
                continue

            # Handle newlines and indentation
            if ch == '\n':
                self.advance()
                # Skip completely empty lines (only newlines)
                while self.peek() == '\n':
                    self.advance()

                # Check if we're at EOF
                if self.peek() == '\0':
                    continue

                # Check if next line is truly blank (only spaces/tabs then newline)
                # Don't consume indentation of the next meaningful line
                peek_pos = self.pos
                while self.source[peek_pos:peek_pos+1] in (' ', '\t'):
                    peek_pos += 1
                if self.source[peek_pos:peek_pos+1] in ('\n', '\0'):
                    # Truly blank line — skip it
                    while self.peek() in (' ', '\t'):
                        self.advance()
                    continue  # Loop back to handle the next newline

                # Measure indentation of the next meaningful line
                indent = 0
                while self.peek() in (' ', '\t'):
                    self.advance()
                    indent += 1

                if self.peek() == '\0' or self.peek() == '\n':
                    continue

                self.tokens.append(Token(TokenType.NEWLINE, '\\n', self.line, 1))

                # Emit INDENT/DEDENT
                if indent > self.indent_stack[-1]:
                    self.indent_stack.append(indent)
                    self.tokens.append(Token(TokenType.INDENT, '->', self.line, 1))
                else:
                    while indent < self.indent_stack[-1]:
                        self.indent_stack.pop()
                        self.tokens.append(Token(TokenType.DEDENT, '<-', self.line, 1))
                continue

            # Handle @approved
            if ch == '@':
                start = self.pos
                self.advance()
                while self.peek().isalpha():
                    self.advance()
                word = self.source[start:self.pos]
                if word == '@approved':
                    self.tokens.append(Token(TokenType.AT_APPROVED, '@approved', self.line, self.col))
                else:
                    self.error(f"Unknown annotation: {word}")
                continue

            # Handle strings
            if ch == '"':
                self.advance()
                start = self.pos
                while self.peek() and self.peek() != '"':
                    if self.peek() == '\\':
                        self.advance()
                    self.advance()
                value = self.source[start:self.pos]
                self.advance()  # skip closing "
                self.tokens.append(Token(TokenType.STRING, value, self.line, self.col))
                continue

            # Handle numbers
            if ch.isdigit():
                start = self.pos
                while self.peek().isdigit():
                    self.advance()
                if self.peek() == '.':
                    self.advance()
                    while self.peek().isdigit():
                        self.advance()
                self.tokens.append(Token(TokenType.NUMBER, self.source[start:self.pos], self.line, self.col))
                continue

            # Handle paths (/something)
            if ch == '/' and self.peek(1).isalpha():
                start = self.pos
                self.advance()
                while self.peek() and (self.peek().isalnum() or self.peek() in '/_-'):
                    self.advance()
                self.tokens.append(Token(TokenType.PATH, self.source[start:self.pos], self.line, self.col))
                continue

            # Handle operators
            two_char = self.source[self.pos:self.pos + 2]
            if two_char == '->':
                self.advance(); self.advance()
                self.tokens.append(Token(TokenType.ARROW, '->', self.line, self.col))
                continue
            if two_char == '==':
                self.advance(); self.advance()
                self.tokens.append(Token(TokenType.EQ, '==', self.line, self.col))
                continue
            if two_char == '!=':
                self.advance(); self.advance()
                self.tokens.append(Token(TokenType.NEQ, '!=', self.line, self.col))
                continue
            if two_char == '<=':
                self.advance(); self.advance()
                self.tokens.append(Token(TokenType.LTE, '<=', self.line, self.col))
                continue
            if two_char == '>=':
                self.advance(); self.advance()
                self.tokens.append(Token(TokenType.GTE, '>=', self.line, self.col))
                continue

            single = {
                '=': TokenType.ASSIGN, '+': TokenType.PLUS, '-': TokenType.MINUS,
                '*': TokenType.STAR, '/': TokenType.SLASH, '.': TokenType.DOT,
                ':': TokenType.COLON, ',': TokenType.COMMA, '(': TokenType.LPAREN,
                ')': TokenType.RPAREN, '{': TokenType.LBRACE, '}': TokenType.RBRACE,
                '<': TokenType.LT, '>': TokenType.GT,
            }
            if ch in single:
                self.advance()
                self.tokens.append(Token(single[ch], ch, self.line, self.col))
                continue

            # Handle identifiers and keywords
            if ch.isalpha() or ch == '_':
                start = self.pos
                while self.peek() and (self.peek().isalnum() or self.peek() == '_'):
                    self.advance()
                word = self.source[start:self.pos]
                if word in KEYWORDS:
                    self.tokens.append(Token(KEYWORDS[word], word, self.line, self.col))
                else:
                    self.tokens.append(Token(TokenType.IDENT, word, self.line, self.col))
                continue

            self.error(f"Unexpected character: {ch!r}")

        # Final newline + DEDENTs
        if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
            self.tokens.append(Token(TokenType.NEWLINE, '\\n', self.line, 1))
        while self.indent_stack[-1] > 0:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, '<-', self.line, 1))
        self.tokens.append(Token(TokenType.EOF, '', self.line, 1))
        return self.tokens


def lex(source: str) -> List[Token]:
    """Tokenize RECEPT source code."""
    return Lexer(source).tokenize()
