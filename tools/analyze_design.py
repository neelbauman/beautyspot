# tools/analyze_design.py
import ast
from pathlib import Path

class DesignAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.current_class = None
        self.protocols = {}  # {Name: {methods}}
        self.classes = {}    # {Name: {methods}}
        self.relationships = [] # list of (Subject, Object, Type)

    def visit_ClassDef(self, node):
        methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
        
        # Protocolかどうかの判定
        is_protocol = any(
            (isinstance(b, ast.Name) and b.id == "Protocol") or
            (isinstance(b, ast.Attribute) and b.attr == "Protocol")
            for b in node.bases
        )
        
        if is_protocol:
            self.protocols[node.name] = methods - {"__init__", "..."}
        else:
            self.classes[node.name] = methods

        # クラスコンテキストでの内部走査
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_Call(self, node):
        if not self.current_class:
            return

        # 1. 生成関係 (Creates): ClassName(...)
        if isinstance(node.func, ast.Name):
            target = node.func.id
            if target[0].isupper() and target != self.current_class:
                self.relationships.append((self.current_class, target, "creates"))

        # 2. 静的利用・バインド (Uses/Binds): Class.method()
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                target_class = node.func.value.id
                if target_class[0].isupper():
                    rel_type = "binds" if node.func.attr == "bind" else "uses"
                    self.relationships.append((self.current_class, f"{target_class}.{node.func.attr}", rel_type))

        self.generic_visit(node)

def analyze_design(src_dir="src/beautyspot"):
    src_path = Path(src_dir)
    analyzer = DesignAnalyzer()

    # 全ファイルを走査
    for path in src_path.glob("*.py"):
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
            analyzer.visit(tree)

    # 3. 暗黙的準拠の判定 (Implements)
    for class_name, class_methods in analyzer.classes.items():
        for proto_name, proto_methods in analyzer.protocols.items():
            if proto_methods and proto_methods.issubset(class_methods):
                analyzer.relationships.append((class_name, proto_name, "implements"))

    # Mermaid出力
    lines = ["graph LR"]
    # スタイル定義
    lines.append("    classDef protocol fill:#f9f,stroke:#333,stroke-width:2px;")
    
    for proto in analyzer.protocols:
        lines.append(f"    class {proto} protocol;")

    for sub, obj, rel in sorted(list(set(analyzer.relationships))):
        if rel == "implements":
            lines.append(f"    {sub} -. \"implements\" .-> {obj}")
        elif rel == "creates":
            lines.append(f"    {sub} -- \"creates\" --> {obj}")
        elif rel == "binds":
            lines.append(f"    {sub} ==> \"binds\" ==> {obj}")
        elif rel == "uses":
            lines.append(f"    {sub} -. \"uses\" .-> {obj}")
            
    return "\n".join(lines)

if __name__ == "__main__":
    print(analyze_design())

