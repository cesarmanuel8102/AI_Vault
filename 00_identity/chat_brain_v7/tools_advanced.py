"""
Fase 2: Herramientas Avanzadas - Análisis AST y Búsqueda
Nivel OpenCode: Análisis profundo de código Python
"""

import ast
import re
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class FunctionInfo:
    """Información de una función"""
    name: str
    line_start: int
    line_end: int
    args: List[str]
    docstring: Optional[str]
    complexity: int = 0
    calls: List[str] = field(default_factory=list)
    returns: bool = False


@dataclass
class ClassInfo:
    """Información de una clase"""
    name: str
    line_start: int
    line_end: int
    methods: List[FunctionInfo] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)
    docstring: Optional[str] = None


@dataclass
class ImportInfo:
    """Información de imports"""
    module: str
    names: List[str]
    line: int
    is_from: bool = False


@dataclass
class ASTAnalysis:
    """Resultado completo de análisis AST"""
    file_path: str
    total_lines: int
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    complexity_score: int = 0
    dependencies: List[str] = field(default_factory=list)


class ASTAnalyzer:
    """Analizador AST profundo de código Python"""
    
    def __init__(self):
        self.cache = {}
    
    def analyze_file(self, file_path: str) -> ASTAnalysis:
        """Analiza un archivo Python completo"""
        try:
            path = Path(file_path)
            if not path.exists():
                return ASTAnalysis(file_path=file_path, total_lines=0)
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            total_lines = len(lines)
            
            # Parsear AST
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return ASTAnalysis(
                    file_path=file_path,
                    total_lines=total_lines,
                    complexity_score=-1  # Indica error de sintaxis
                )
            
            # Analizar
            functions = []
            classes = []
            imports = []
            dependencies = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_info = self._analyze_function(node, content)
                    functions.append(func_info)
                
                elif isinstance(node, ast.ClassDef):
                    class_info = self._analyze_class(node, content)
                    classes.append(class_info)
                
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(ImportInfo(
                            module=alias.name,
                            names=[alias.asname or alias.name],
                            line=node.lineno,
                            is_from=False
                        ))
                        dependencies.append(alias.name)
                
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = [alias.name for alias in node.names]
                    imports.append(ImportInfo(
                        module=module,
                        names=names,
                        line=node.lineno,
                        is_from=True
                    ))
                    dependencies.append(module)
            
            # Calcular complejidad
            complexity = sum(f.complexity for f in functions)
            
            return ASTAnalysis(
                file_path=file_path,
                total_lines=total_lines,
                functions=functions,
                classes=classes,
                imports=imports,
                complexity_score=complexity,
                dependencies=list(set(dependencies))
            )
            
        except Exception as e:
            return ASTAnalysis(
                file_path=file_path,
                total_lines=0,
                complexity_score=-2  # Error general
            )
    
    def _analyze_function(self, node: ast.FunctionDef, content: str) -> FunctionInfo:
        """Analiza una función"""
        # Obtener líneas
        line_start = node.lineno
        line_end = node.end_lineno or line_start
        
        # Obtener argumentos
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        
        # Obtener docstring
        docstring = ast.get_docstring(node)
        
        # Calcular complejidad ciclomática básica
        complexity = 1  # Base
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        # Encontrar llamadas a funciones
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        
        # Verificar si retorna valores
        returns = any(isinstance(child, ast.Return) and child.value is not None 
                     for child in ast.walk(node))
        
        return FunctionInfo(
            name=node.name,
            line_start=line_start,
            line_end=line_end,
            args=args,
            docstring=docstring,
            complexity=complexity,
            calls=list(set(calls)),
            returns=returns
        )
    
    def _analyze_class(self, node: ast.ClassDef, content: str) -> ClassInfo:
        """Analiza una clase"""
        line_start = node.lineno
        line_end = node.end_lineno or line_start
        
        # Obtener docstring
        docstring = ast.get_docstring(node)
        
        # Obtener bases
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{base.value.id}.{base.attr}" if isinstance(base.value, ast.Name) else base.attr)
        
        # Analizar métodos
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_info = self._analyze_function(item, content)
                methods.append(method_info)
        
        return ClassInfo(
            name=node.name,
            line_start=line_start,
            line_end=line_end,
            methods=methods,
            bases=bases,
            docstring=docstring
        )
    
    def find_symbol(self, symbol_name: str, path: str) -> List[Dict]:
        """Busca definición de un símbolo"""
        results = []
        
        for py_file in Path(path).rglob("*.py"):
            try:
                analysis = self.analyze_file(str(py_file))
                
                # Buscar en funciones
                for func in analysis.functions:
                    if func.name == symbol_name:
                        results.append({
                            "type": "function",
                            "file": str(py_file),
                            "line": func.line_start,
                            "info": func
                        })
                
                # Buscar en clases
                for cls in analysis.classes:
                    if cls.name == symbol_name:
                        results.append({
                            "type": "class",
                            "file": str(py_file),
                            "line": cls.line_start,
                            "info": cls
                        })
                    
                    # Buscar en métodos
                    for method in cls.methods:
                        if method.name == symbol_name:
                            results.append({
                                "type": "method",
                                "class": cls.name,
                                "file": str(py_file),
                                "line": method.line_start,
                                "info": method
                            })
                
            except Exception:
                continue
        
        return results
    
    def find_references(self, symbol_name: str, path: str) -> List[Dict]:
        """Busca referencias a un símbolo"""
        results = []
        
        for py_file in Path(path).rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Buscar patrones de uso
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    # Patrones comunes de uso
                    patterns = [
                        rf'\b{re.escape(symbol_name)}\s*\(',  # Llamada a función
                        rf'\b{re.escape(symbol_name)}\.',     # Acceso a atributo
                        rf'\b{re.escape(symbol_name)}\s*=',    # Asignación
                        rf'\b{re.escape(symbol_name)}\b',      # Referencia general
                    ]
                    
                    for pattern in patterns:
                        if re.search(pattern, line):
                            # Verificar que no es la definición
                            if not re.match(rf'^\s*(def|class)\s+{re.escape(symbol_name)}', line):
                                results.append({
                                    "file": str(py_file),
                                    "line": i,
                                    "content": line.strip()
                                })
                                break
                
            except Exception:
                continue
        
        return results
    
    def calculate_metrics(self, file_path: str) -> Dict:
        """Calcula métricas de código"""
        analysis = self.analyze_file(file_path)
        
        if analysis.complexity_score < 0:
            return {"error": "Syntax error or file not found"}
        
        # Calcular métricas
        total_functions = len(analysis.functions)
        total_classes = len(analysis.classes)
        total_imports = len(analysis.imports)
        
        avg_complexity = (analysis.complexity_score / total_functions) if total_functions > 0 else 0
        
        # Funciones sin docstring
        funcs_no_doc = sum(1 for f in analysis.functions if not f.docstring)
        doc_coverage = ((total_functions - funcs_no_doc) / total_functions * 100) if total_functions > 0 else 0
        
        # Líneas de código reales (sin imports y docstrings)
        loc = analysis.total_lines
        
        return {
            "file": file_path,
            "total_lines": analysis.total_lines,
            "functions": total_functions,
            "classes": total_classes,
            "imports": total_imports,
            "complexity_score": analysis.complexity_score,
            "avg_complexity": round(avg_complexity, 2),
            "docstring_coverage": round(doc_coverage, 1),
            "dependencies": len(analysis.dependencies),
            "loc": loc
        }


class AdvancedSearch:
    """Búsqueda avanzada tipo grep/glob"""
    
    def __init__(self):
        self.results_cache = {}
    
    def grep(self, pattern: str, path: str, recursive: bool = True, 
             file_pattern: str = "*.py") -> List[Dict]:
        """
        Busca patrones en contenido de archivos
        Equivalente a: grep -r "pattern" path
        """
        results = []
        path_obj = Path(path)
        
        if not path_obj.exists():
            return results
        
        # Compilar regex
        try:
            regex = re.compile(pattern)
        except re.error:
            # Si no es regex válido, buscar literal
            regex = re.compile(re.escape(pattern))
        
        # Buscar archivos
        if recursive:
            files = list(path_obj.rglob(file_pattern))
        else:
            files = [f for f in path_obj.iterdir() if f.match(file_pattern)]
        
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines, 1):
                        if regex.search(line):
                            results.append({
                                "file": str(file_path),
                                "line": i,
                                "content": line.strip(),
                                "match": regex.search(line).group(0) if regex.search(line) else ""
                            })
            except Exception:
                continue
        
        return results
    
    def glob_files(self, pattern: str, path: str) -> List[str]:
        """
        Encuentra archivos por patrón glob
        Equivalente a: find path -name "pattern"
        """
        results = []
        path_obj = Path(path)
        
        if not path_obj.exists():
            return results
        
        # Convertir patrón glob a regex
        regex_pattern = pattern.replace(".", r"\.")
        regex_pattern = regex_pattern.replace("*", ".*")
        regex_pattern = regex_pattern.replace("?", ".")
        
        try:
            regex = re.compile(regex_pattern)
        except re.error:
            return results
        
        for file_path in path_obj.rglob("*"):
            if file_path.is_file() and regex.match(file_path.name):
                results.append(str(file_path))
        
        return sorted(results)
    
    def find_by_content_type(self, content_type: str, path: str) -> List[str]:
        """Encuentra archivos por tipo de contenido"""
        type_patterns = {
            "python": "*.py",
            "json": "*.json",
            "markdown": "*.md",
            "config": "*.toml,*.yaml,*.yml,*.ini",
            "test": "*test*.py",
            "documentation": "*.md,*.rst,*.txt"
        }
        
        pattern = type_patterns.get(content_type, "*")
        
        if "," in pattern:
            results = []
            for p in pattern.split(","):
                results.extend(self.glob_files(p.strip(), path))
            return results
        else:
            return self.glob_files(pattern, path)


class SmartEditor:
    """Edición inteligente de código"""
    
    def __init__(self):
        self.analyzer = ASTAnalyzer()
    
    def insert_import(self, file_path: str, import_statement: str) -> bool:
        """Inserta un import ordenado alfabéticamente"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            # Encontrar línea de imports existentes
            import_lines = []
            other_lines = []
            
            for i, line in enumerate(lines):
                if line.strip().startswith(('import ', 'from ')):
                    import_lines.append((i, line))
                else:
                    other_lines.append(line)
            
            if not import_lines:
                # No hay imports, insertar al principio
                new_lines = [import_statement, ''] + lines
            else:
                # Insertar ordenado
                new_imports = [imp[1] for imp in import_lines]
                new_imports.append(import_statement)
                new_imports.sort(key=lambda x: x.lower())
                
                # Reconstruir archivo
                first_import_line = import_lines[0][0]
                new_lines = lines[:first_import_line]
                new_lines.extend(new_imports)
                new_lines.extend(lines[import_lines[-1][0]+1:])
            
            # Escribir
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            return True
            
        except Exception as e:
            print(f"[ERROR] No se pudo insertar import: {e}")
            return False
    
    def extract_function(self, file_path: str, func_name: str, 
                        new_file: str = None) -> bool:
        """Extrae una función a un nuevo archivo"""
        try:
            analysis = self.analyzer.analyze_file(file_path)
            
            # Encontrar función
            target_func = None
            for func in analysis.functions:
                if func.name == func_name:
                    target_func = func
                    break
            
            if not target_func:
                return False
            
            # Leer contenido original
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            # Extraer función
            func_lines = lines[target_func.line_start-1:target_func.line_end]
            func_code = '\n'.join(func_lines)
            
            # Determinar nuevo archivo
            if new_file is None:
                new_file = file_path.replace('.py', f'_{func_name}.py')
            
            # Crear nuevo archivo con imports necesarios
            new_content = f"# Extracted from {file_path}\n\n"
            new_content += func_code + '\n'
            
            with open(new_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] No se pudo extraer función: {e}")
            return False
    
    def add_function(self, file_path: str, function_code: str, 
                    position: str = "end") -> bool:
        """Agrega una función al archivo"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if position == "end":
                # Agregar al final
                if not content.endswith('\n'):
                    content += '\n'
                content += '\n' + function_code + '\n'
            else:
                # Insertar en posición específica (línea)
                lines = content.split('\n')
                pos = int(position) if position.isdigit() else len(lines)
                lines.insert(pos, function_code)
                content = '\n'.join(lines)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] No se pudo agregar función: {e}")
            return False


# Funciones de conveniencia para ToolRegistry
def analyze_code_structure(file_path: str) -> Dict:
    """Analiza estructura de código Python"""
    analyzer = ASTAnalyzer()
    analysis = analyzer.analyze_file(file_path)
    
    return {
        "success": True,
        "file": file_path,
        "total_lines": analysis.total_lines,
        "functions": [
            {
                "name": f.name,
                "line": f.line_start,
                "args": f.args,
                "complexity": f.complexity,
                "docstring": f.docstring is not None
            }
            for f in analysis.functions
        ],
        "classes": [
            {
                "name": c.name,
                "line": c.line_start,
                "methods": len(c.methods),
                "bases": c.bases
            }
            for c in analysis.classes
        ],
        "imports": [
            {
                "module": i.module,
                "names": i.names,
                "line": i.line
            }
            for i in analysis.imports
        ],
        "complexity_score": analysis.complexity_score,
        "dependencies": analysis.dependencies
    }


def grep(pattern: str, path: str, recursive: bool = True) -> Dict:
    """Busca patrones en archivos"""
    searcher = AdvancedSearch()
    results = searcher.grep(pattern, path, recursive)
    
    return {
        "success": True,
        "pattern": pattern,
        "path": path,
        "matches": len(results),
        "results": results[:50]  # Limitar a 50 resultados
    }


def glob_files(pattern: str, path: str) -> Dict:
    """Encuentra archivos por patrón"""
    searcher = AdvancedSearch()
    results = searcher.glob_files(pattern, path)
    
    return {
        "success": True,
        "pattern": pattern,
        "path": path,
        "files": results,
        "count": len(results)
    }


def find_symbol(symbol_name: str, path: str) -> Dict:
    """Busca definición de símbolo"""
    analyzer = ASTAnalyzer()
    results = analyzer.find_symbol(symbol_name, path)
    
    return {
        "success": True,
        "symbol": symbol_name,
        "path": path,
        "definitions": len(results),
        "results": results
    }


def find_references(symbol_name: str, path: str) -> Dict:
    """Busca referencias a símbolo"""
    analyzer = ASTAnalyzer()
    results = analyzer.find_references(symbol_name, path)
    
    return {
        "success": True,
        "symbol": symbol_name,
        "path": path,
        "references": len(results),
        "results": results[:30]  # Limitar a 30
    }


def calculate_code_metrics(file_path: str) -> Dict:
    """Calcula métricas de código"""
    analyzer = ASTAnalyzer()
    metrics = analyzer.calculate_metrics(file_path)
    
    return {
        "success": "error" not in metrics,
        "file": file_path,
        "metrics": metrics
    }


# Exportar todo
__all__ = [
    'ASTAnalyzer',
    'ASTAnalysis',
    'FunctionInfo',
    'ClassInfo',
    'ImportInfo',
    'AdvancedSearch',
    'SmartEditor',
    'analyze_code_structure',
    'grep',
    'glob_files',
    'find_symbol',
    'find_references',
    'calculate_code_metrics'
]


if __name__ == "__main__":
    # Test básico
    print("Testing AST Analyzer...")
    
    analyzer = ASTAnalyzer()
    
    # Analizar este archivo
    result = analyzer.analyze_file(__file__)
    print(f"\nAnalyzed: {__file__}")
    print(f"  Lines: {result.total_lines}")
    print(f"  Functions: {len(result.functions)}")
    print(f"  Classes: {len(result.classes)}")
    print(f"  Complexity: {result.complexity_score}")
    
    if result.functions:
        print(f"\nFunctions found:")
        for func in result.functions[:5]:
            print(f"  - {func.name} (line {func.line_start}, complexity {func.complexity})")
    
    # Test search
    print("\nTesting search...")
    searcher = AdvancedSearch()
    results = searcher.grep("def ", Path(__file__).parent, file_pattern="*.py")
    print(f"Found {len(results)} function definitions")
