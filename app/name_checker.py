import ast
import builtins


class NameChecker(ast.NodeVisitor):
    def __init__(self):
        self.defined_names = set()
        self.errors = []

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.defined_names.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            if node.id not in self.defined_names and node.id not in dir(builtins):
                self.errors.append((node.id, node.lineno, node.col_offset))

    def visit_Import(self, node):
        for alias in node.names:
            self.defined_names.add(alias.asname or alias.name.split('.')[0])

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.defined_names.add(alias.asname or alias.name)

    def visit_comprehension(self, node):  # type: (ast.AST) -> None
        self.visit(node.target)  # Track loop variables
        self.visit(node.iter)
        for if_clause in node.ifs:
            self.visit(if_clause)

    def visit_ListComp(self, node):  # type: (ast.AST) -> None
        for gen in node.generators:
            self.visit(gen)
        self.visit(node.elt)

    def visit_SetComp(self, node):  # type: (ast.AST) -> None
        for gen in node.generators:
            self.visit(gen)
        self.visit(node.elt)

    def visit_DictComp(self, node):  # type: (ast.AST) -> None
        for gen in node.generators:
            self.visit(gen)
        self.visit(node.key)
        self.visit(node.value)

    def visit_GeneratorExp(self, node):  # type: (ast.AST) -> None
        for gen in node.generators:
            self.visit(gen)
        self.visit(node.elt)

    def visit_FunctionDef(self, node):
        self.defined_names.add(node.name)
        self.defined_names.add(node.name)  # add function name itself
        # Add all function arguments
        for arg in node.args.args:
            self.defined_names.add(arg.arg)

        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_Module(self, node):
        # First collect all top-level function/class names
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.ClassDef)):
                self.defined_names.add(stmt.name)
        # Then visit all
        self.generic_visit(node)
