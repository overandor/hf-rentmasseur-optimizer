"""RECEPT Parser — builds AST from token stream."""

from dataclasses import dataclass, field
from typing import List, Optional, Any
from .lexer import Token, TokenType, lex


@dataclass
class Node:
    line: int = 0


@dataclass
class CapsuleDecl(Node):
    name: str = ""


@dataclass
class ObserveBlock(Node):
    statements: List[Any] = field(default_factory=list)


@dataclass
class DecideBlock(Node):
    statements: List[Any] = field(default_factory=list)


@dataclass
class ExecuteBlock(Node):
    statements: List[Any] = field(default_factory=list)


@dataclass
class EndpointDecl(Node):
    method: str = ""
    path: str = ""
    statements: List[Any] = field(default_factory=list)
    return_value: Optional[Any] = None


@dataclass
class WorkflowDecl(Node):
    name: str = ""
    steps: List[Any] = field(default_factory=list)


@dataclass
class StepDecl(Node):
    number: int = 0
    action: str = ""


@dataclass
class FnDecl(Node):
    name: str = ""
    params: List[tuple] = field(default_factory=list)  # (name, type)
    return_type: str = "none"
    body: List[Any] = field(default_factory=list)
    approved: bool = False


@dataclass
class IfStmt(Node):
    condition: Any = None
    then_body: List[Any] = field(default_factory=list)
    else_body: List[Any] = field(default_factory=list)


@dataclass
class ReturnStmt(Node):
    value: Any = None


@dataclass
class AssignStmt(Node):
    target: str = ""
    value: Any = None


@dataclass
class CallExpr(Node):
    func: str = ""
    args: List[Any] = field(default_factory=list)


@dataclass
class MethodCall(Node):
    obj: str = ""
    method: str = ""
    args: List[Any] = field(default_factory=list)


@dataclass
class BinaryOp(Node):
    op: str = ""
    left: Any = None
    right: Any = None


@dataclass
class StringLit(Node):
    value: str = ""


@dataclass
class NumberLit(Node):
    value: float = 0


@dataclass
class BoolLit(Node):
    value: bool = False


@dataclass
class NoneLit(Node):
    pass


@dataclass
class IdentRef(Node):
    name: str = ""


@dataclass
class ReceiptStmt(Node):
    text: Any = None


@dataclass
class DictLit(Node):
    pairs: List[tuple] = field(default_factory=list)  # (key, value)


class Parser:
    """Parses RECEPT tokens into an AST."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset=0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def advance(self) -> Token:
        tok = self.peek()
        self.pos += 1
        return tok

    def expect(self, ttype: TokenType) -> Token:
        tok = self.peek()
        if tok.type != ttype:
            raise SyntaxError(f"RECEPT Parse Error at line {tok.line}: expected {ttype.name}, got {tok.type.name} ({tok.value!r})")
        return self.advance()

    def skip_newlines(self):
        while self.peek().type == TokenType.NEWLINE:
            self.advance()

    def parse(self) -> List[Node]:
        """Parse entire program."""
        declarations: List[Node] = []
        self.skip_newlines()

        while self.peek().type != TokenType.EOF:
            node = self.parse_declaration()
            if node:
                declarations.append(node)
            self.skip_newlines()

        return declarations

    def parse_declaration(self) -> Optional[Node]:
        tok = self.peek()

        if tok.type == TokenType.CAPSULE:
            return self.parse_capsule()
        elif tok.type == TokenType.OBSERVE:
            return self.parse_observe()
        elif tok.type == TokenType.DECIDE:
            return self.parse_decide()
        elif tok.type == TokenType.EXECUTE:
            return self.parse_execute()
        elif tok.type == TokenType.ENDPOINT:
            return self.parse_endpoint()
        elif tok.type == TokenType.WORKFLOW:
            return self.parse_workflow()
        elif tok.type == TokenType.AT_APPROVED:
            return self.parse_fn(approved=True)
        elif tok.type == TokenType.FN:
            return self.parse_fn(approved=False)
        elif tok.type == TokenType.EOF:
            return None
        else:
            raise SyntaxError(f"RECEPT Parse Error at line {tok.line}: unexpected token {tok.type.name} ({tok.value!r})")

    def parse_capsule(self) -> CapsuleDecl:
        tok = self.expect(TokenType.CAPSULE)
        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.NEWLINE)
        return CapsuleDecl(name=name, line=tok.line)

    def parse_block(self) -> List[Any]:
        """Parse an indented block of statements."""
        self.expect(TokenType.COLON)
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        statements = []
        while self.peek().type != TokenType.DEDENT and self.peek().type != TokenType.EOF:
            self.skip_newlines()
            if self.peek().type == TokenType.DEDENT or self.peek().type == TokenType.EOF:
                break
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)

        if self.peek().type == TokenType.DEDENT:
            self.advance()
        return statements

    def parse_observe(self) -> ObserveBlock:
        tok = self.expect(TokenType.OBSERVE)
        stmts = self.parse_block()
        return ObserveBlock(statements=stmts, line=tok.line)

    def parse_decide(self) -> DecideBlock:
        tok = self.expect(TokenType.DECIDE)
        stmts = self.parse_block()
        return DecideBlock(statements=stmts, line=tok.line)

    def parse_execute(self) -> ExecuteBlock:
        tok = self.expect(TokenType.EXECUTE)
        stmts = self.parse_block()
        return ExecuteBlock(statements=stmts, line=tok.line)

    def parse_endpoint(self) -> EndpointDecl:
        tok = self.expect(TokenType.ENDPOINT)
        method_tok = self.peek()
        method = method_tok.value
        if method_tok.type in (TokenType.GET, TokenType.POST, TokenType.PUT, TokenType.DELETE):
            self.advance()
        else:
            raise SyntaxError(f"Expected HTTP method, got {method_tok.type.name}")

        path = self.expect(TokenType.PATH).value
        stmts = self.parse_block()

        return_value = None
        for s in stmts:
            if isinstance(s, ReturnStmt):
                return_value = s.value
                break

        return EndpointDecl(method=method, path=path, statements=stmts, return_value=return_value, line=tok.line)

    def parse_workflow(self) -> WorkflowDecl:
        tok = self.expect(TokenType.WORKFLOW)
        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.COLON)
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        steps = []
        while self.peek().type != TokenType.DEDENT and self.peek().type != TokenType.EOF:
            self.skip_newlines()
            if self.peek().type == TokenType.DEDENT or self.peek().type == TokenType.EOF:
                break
            if self.peek().type == TokenType.STEP:
                self.advance()
                num = int(self.expect(TokenType.NUMBER).value)
                self.expect(TokenType.COLON)
                action_parts = []
                while self.peek().type not in (TokenType.NEWLINE, TokenType.EOF):
                    action_parts.append(self.advance().value)
                action = ' '.join(action_parts)
                steps.append(StepDecl(number=num, action=action, line=tok.line))
            self.skip_newlines()

        if self.peek().type == TokenType.DEDENT:
            self.advance()
        return WorkflowDecl(name=name, steps=steps, line=tok.line)

    def parse_fn(self, approved=False) -> FnDecl:
        tok = self.peek()
        if approved:
            self.expect(TokenType.AT_APPROVED)
            self.skip_newlines()
        self.expect(TokenType.FN)
        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.LPAREN)

        params = []
        while self.peek().type != TokenType.RPAREN:
            pname = self.expect(TokenType.IDENT).value
            ptype = "any"
            if self.peek().type == TokenType.COLON:
                self.advance()
                # Type can be a keyword type or an identifier
                type_tok = self.peek()
                if type_tok.type in (TokenType.TYPE_TEXT, TokenType.TYPE_INT, TokenType.TYPE_BOOL,
                                     TokenType.TYPE_ARTIFACT, TokenType.TYPE_RECEIPT,
                                     TokenType.TYPE_ENDPOINT, TokenType.TYPE_NONE, TokenType.IDENT):
                    ptype = self.advance().value
                else:
                    ptype = self.advance().value
            params.append((pname, ptype))
            if self.peek().type == TokenType.COMMA:
                self.advance()

        self.expect(TokenType.RPAREN)

        return_type = "none"
        if self.peek().type == TokenType.ARROW:
            self.advance()
            type_tok = self.peek()
            if type_tok.type in (TokenType.TYPE_TEXT, TokenType.TYPE_INT, TokenType.TYPE_BOOL,
                                 TokenType.TYPE_ARTIFACT, TokenType.TYPE_RECEIPT,
                                 TokenType.TYPE_ENDPOINT, TokenType.TYPE_NONE, TokenType.IDENT):
                return_type = self.advance().value
            else:
                return_type = self.advance().value

        body = self.parse_block()
        return FnDecl(name=name, params=params, return_type=return_type, body=body, approved=approved, line=tok.line)

    def parse_statement(self) -> Optional[Any]:
        tok = self.peek()

        if tok.type == TokenType.IF:
            return self.parse_if()
        elif tok.type == TokenType.RETURN:
            return self.parse_return()
        elif tok.type == TokenType.RECEIPT:
            return self.parse_receipt()
        elif tok.type == TokenType.IDENT:
            return self.parse_assignment_or_call()
        else:
            raise SyntaxError(f"RECEPT Parse Error at line {tok.line}: unexpected statement {tok.type.name} ({tok.value!r})")

    def parse_if(self) -> IfStmt:
        tok = self.expect(TokenType.IF)
        condition = self.parse_expression()
        then_body = self.parse_block()

        else_body = []
        self.skip_newlines()
        if self.peek().type == TokenType.ELSE:
            self.advance()
            else_body = self.parse_block()

        return IfStmt(condition=condition, then_body=then_body, else_body=else_body, line=tok.line)

    def parse_return(self) -> ReturnStmt:
        tok = self.expect(TokenType.RETURN)
        value = None
        if self.peek().type != TokenType.NEWLINE:
            value = self.parse_expression()
        self.expect(TokenType.NEWLINE)
        return ReturnStmt(value=value, line=tok.line)

    def parse_receipt(self) -> ReceiptStmt:
        tok = self.expect(TokenType.RECEIPT)
        text = self.parse_expression()
        self.expect(TokenType.NEWLINE)
        return ReceiptStmt(text=text, line=tok.line)

    def parse_assignment_or_call(self) -> Any:
        tok = self.peek()
        name = self.advance().value

        if self.peek().type == TokenType.ASSIGN:
            self.advance()
            value = self.parse_expression()
            self.expect(TokenType.NEWLINE)
            return AssignStmt(target=name, value=value, line=tok.line)

        if self.peek().type == TokenType.LPAREN:
            args = self.parse_args()
            self.expect(TokenType.NEWLINE)
            return CallExpr(func=name, args=args, line=tok.line)

        if self.peek().type == TokenType.DOT:
            self.advance()
            method = self.expect(TokenType.IDENT).value
            args = []
            if self.peek().type == TokenType.LPAREN:
                args = self.parse_args()
            self.expect(TokenType.NEWLINE)
            return MethodCall(obj=name, method=method, args=args, line=tok.line)

        self.expect(TokenType.NEWLINE)
        return IdentRef(name=name, line=tok.line)

    def parse_args(self) -> List[Any]:
        self.expect(TokenType.LPAREN)
        args = []
        while self.peek().type != TokenType.RPAREN:
            # Check for named argument: ident = value
            if self.peek().type == TokenType.IDENT and self.peek(1).type == TokenType.ASSIGN:
                self.advance()  # ident
                self.advance()  # =
                args.append(self.parse_expression())
            else:
                args.append(self.parse_expression())
            if self.peek().type == TokenType.COMMA:
                self.advance()
        self.expect(TokenType.RPAREN)
        return args

    def parse_expression(self) -> Any:
        return self.parse_binary_op(0)

    def parse_binary_op(self, min_prec: int) -> Any:
        left = self.parse_primary()

        prec_map = {
            TokenType.PLUS: 1, TokenType.MINUS: 1,
            TokenType.STAR: 2, TokenType.SLASH: 2,
            TokenType.EQ: 3, TokenType.NEQ: 3,
            TokenType.LT: 3, TokenType.GT: 3,
            TokenType.LTE: 3, TokenType.GTE: 3,
            TokenType.AND: 4,
            TokenType.OR: 5,
        }

        while True:
            tok = self.peek()
            if tok.type not in prec_map:
                break
            prec = prec_map[tok.type]
            if prec < min_prec:
                break
            op = self.advance().value
            right = self.parse_binary_op(prec + 1)
            left = BinaryOp(op=op, left=left, right=right, line=tok.line)

        return left

    def parse_primary(self) -> Any:
        tok = self.peek()

        if tok.type == TokenType.STRING:
            self.advance()
            return StringLit(value=tok.value, line=tok.line)
        elif tok.type == TokenType.NUMBER:
            self.advance()
            return NumberLit(value=float(tok.value), line=tok.line)
        elif tok.type == TokenType.TRUE:
            self.advance()
            return BoolLit(value=True, line=tok.line)
        elif tok.type == TokenType.FALSE:
            self.advance()
            return BoolLit(value=False, line=tok.line)
        elif tok.type == TokenType.NONE:
            self.advance()
            return NoneLit(line=tok.line)
        elif tok.type == TokenType.IDENT:
            self.advance()
            if self.peek().type == TokenType.LPAREN:
                args = self.parse_args()
                return CallExpr(func=tok.value, args=args, line=tok.line)
            if self.peek().type == TokenType.DOT:
                self.advance()
                method = self.expect(TokenType.IDENT).value
                args = []
                if self.peek().type == TokenType.LPAREN:
                    args = self.parse_args()
                return MethodCall(obj=tok.value, method=method, args=args, line=tok.line)
            return IdentRef(name=tok.value, line=tok.line)
        elif tok.type == TokenType.LBRACE:
            return self.parse_dict()
        elif tok.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr
        else:
            raise SyntaxError(f"RECEPT Parse Error at line {tok.line}: unexpected expression token {tok.type.name} ({tok.value!r})")

    def parse_dict(self) -> DictLit:
        tok = self.expect(TokenType.LBRACE)
        pairs = []
        while self.peek().type != TokenType.RBRACE:
            key = self.advance().value
            self.expect(TokenType.COLON)
            value = self.parse_expression()
            pairs.append((key, value))
            if self.peek().type == TokenType.COMMA:
                self.advance()
        self.expect(TokenType.RBRACE)
        return DictLit(pairs=pairs, line=tok.line)


def parse(source: str) -> List[Node]:
    """Parse RECEPT source code into an AST."""
    tokens = lex(source)
    return Parser(tokens).parse()
