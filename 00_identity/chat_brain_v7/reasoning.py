"""
Fase 3: Razonamiento Complejo
Debug, Refactorización, Generación de Código
"""

import ast
import re
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Importar herramientas avanzadas
sys.path.insert(0, str(Path(__file__).parent))
try:
    from tools_advanced import ASTAnalyzer, AdvancedSearch, SmartEditor
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False
    print("[WARNING] tools_advanced not available")


@dataclass
class Hypothesis:
    """Hipótesis de solución"""
    description: str
    confidence: float
    action: str
    params: Dict
    verification: str


@dataclass
class DebugResult:
    """Resultado de debugging"""
    error: str
    root_cause: str
    hypotheses: List[Hypothesis]
    solution: Optional[str] = None
    fixed: bool = False


class DebugReasoner:
    """Razonador para debugging automático"""
    
    def __init__(self):
        self.analyzer = ASTAnalyzer() if TOOLS_AVAILABLE else None
        self.searcher = AdvancedSearch() if TOOLS_AVAILABLE else None
    
    def analyze_error(self, error_message: str, stack_trace: str = "", 
                     file_path: str = "") -> DebugResult:
        """
        Analiza un error y propone soluciones
        
        Proceso:
        1. Parsear error y stack trace
        2. Identificar archivo/función problemática
        3. Analizar código con AST
        4. Generar hipótesis
        5. Proponer soluciones ordenadas por probabilidad
        """
        # Paso 1: Parsear error
        error_type, error_detail = self._parse_error(error_message)
        
        # Paso 2: Extraer ubicación del stack trace
        location = self._extract_location(stack_trace)
        
        # Paso 3: Analizar código si tenemos archivo
        code_analysis = None
        if file_path and Path(file_path).exists():
            code_analysis = self.analyzer.analyze_file(file_path) if self.analyzer else None
        
        # Paso 4: Generar hipótesis basadas en tipo de error
        hypotheses = self._generate_hypotheses(
            error_type, 
            error_detail, 
            location,
            code_analysis
        )
        
        # Paso 5: Encontrar root cause más probable
        root_cause = self._identify_root_cause(error_type, error_detail, hypotheses)
        
        return DebugResult(
            error=error_message,
            root_cause=root_cause,
            hypotheses=hypotheses,
            solution=hypotheses[0].description if hypotheses else None,
            fixed=False
        )
    
    def _parse_error(self, error_message: str) -> Tuple[str, str]:
        """Parsea el mensaje de error"""
        # Patrones comunes de errores Python
        patterns = [
            (r'NameError:\s*(.+)', 'NameError'),
            (r'ImportError:\s*(.+)', 'ImportError'),
            (r'ModuleNotFoundError:\s*(.+)', 'ModuleNotFoundError'),
            (r'SyntaxError:\s*(.+)', 'SyntaxError'),
            (r'AttributeError:\s*(.+)', 'AttributeError'),
            (r'KeyError:\s*(.+)', 'KeyError'),
            (r'IndexError:\s*(.+)', 'IndexError'),
            (r'TypeError:\s*(.+)', 'TypeError'),
            (r'ValueError:\s*(.+)', 'ValueError'),
        ]
        
        for pattern, error_type in patterns:
            match = re.search(pattern, error_message)
            if match:
                return error_type, match.group(1).strip()
        
        return "Unknown", error_message
    
    def _extract_location(self, stack_trace: str) -> Dict:
        """Extrae ubicación del stack trace"""
        location = {
            "file": None,
            "line": None,
            "function": None
        }
        
        # Buscar último frame
        lines = stack_trace.split('\n')
        for i, line in enumerate(lines):
            # Patrón: File "path", line X, in function
            match = re.search(r'File "(.+)", line (\d+), in (.+)', line)
            if match:
                location["file"] = match.group(1)
                location["line"] = int(match.group(2))
                location["function"] = match.group(3)
        
        return location
    
    def _generate_hypotheses(self, error_type: str, error_detail: str,
                           location: Dict, code_analysis: Any) -> List[Hypothesis]:
        """Genera hipótesis basadas en el tipo de error"""
        hypotheses = []
        
        if error_type == "NameError":
            # Variable no definida
            var_name = error_detail.strip("'")
            hypotheses.append(Hypothesis(
                description=f"Variable '{var_name}' no definida. Verificar typo o inicialización.",
                confidence=0.9,
                action="search_definition",
                params={"symbol": var_name},
                verification=f"Variable {var_name} definida"
            ))
            hypotheses.append(Hypothesis(
                description=f"Falta import. Buscar '{var_name}' en imports.",
                confidence=0.7,
                action="add_import",
                params={"module": var_name},
                verification=f"Import agregado"
            ))
        
        elif error_type == "ImportError" or error_type == "ModuleNotFoundError":
            module = error_detail.split("'")[1] if "'" in error_detail else error_detail
            hypotheses.append(Hypothesis(
                description=f"Módulo '{module}' no encontrado. Instalar con pip.",
                confidence=0.95,
                action="install_package",
                params={"package": module},
                verification=f"Módulo {module} instalado"
            ))
            hypotheses.append(Hypothesis(
                description=f"Typo en nombre de módulo. Verificar spelling.",
                confidence=0.6,
                action="search_similar",
                params={"name": module},
                verification="Módulo correcto encontrado"
            ))
        
        elif error_type == "AttributeError":
            # Atributo no existe
            match = re.search(r"'(.+)' object has no attribute '(.+)'", error_detail)
            if match:
                obj_type, attr = match.groups()
                hypotheses.append(Hypothesis(
                    description=f"Atributo '{attr}' no existe en {obj_type}. Verificar typo.",
                    confidence=0.85,
                    action="fix_attribute",
                    params={"object": obj_type, "attribute": attr},
                    verification=f"Atributo corregido"
                ))
        
        elif error_type == "KeyError":
            key = error_detail.strip("'")
            hypotheses.append(Hypothesis(
                description=f"Clave '{key}' no existe en diccionario. Usar .get() o verificar.",
                confidence=0.9,
                action="fix_key_access",
                params={"key": key},
                verification="Acceso a clave seguro"
            ))
        
        elif error_type == "SyntaxError":
            hypotheses.append(Hypothesis(
                description="Error de sintaxis. Revisar línea indicada.",
                confidence=0.95,
                action="fix_syntax",
                params={"line": location.get("line")},
                verification="Sintaxis corregida"
            ))
        
        # Siempre agregar hipótesis genérica
        hypotheses.append(Hypothesis(
            description="Error desconocido. Revisar código manualmente.",
            confidence=0.3,
            action="manual_review",
            params={},
            verification="Revisión completada"
        ))
        
        return sorted(hypotheses, key=lambda h: h.confidence, reverse=True)
    
    def _identify_root_cause(self, error_type: str, error_detail: str,
                           hypotheses: List[Hypothesis]) -> str:
        """Identifica la causa raíz más probable"""
        if hypotheses:
            return hypotheses[0].description
        return f"{error_type}: {error_detail}"
    
    def suggest_fix(self, error_message: str, file_path: str) -> Optional[str]:
        """Sugiere un fix específico para el error"""
        error_type, error_detail = self._parse_error(error_message)
        
        if error_type == "NameError":
            var_name = error_detail.strip("'")
            return f"# Verificar que '{var_name}' esté definida antes de usarla\n# o agregar: {var_name} = None  # inicialización"
        
        elif error_type in ["ImportError", "ModuleNotFoundError"]:
            module = error_detail.split("'")[1] if "'" in error_detail else error_detail
            return f"# Instalar módulo faltante:\n# pip install {module}"
        
        elif error_type == "AttributeError":
            return "# Verificar que el objeto tenga el atributo antes de accederlo\n# o usar getattr(obj, 'attr', default)"
        
        elif error_type == "KeyError":
            return "# Usar .get() para acceso seguro a diccionarios:\n# value = dict.get('key', default_value)"
        
        return None


class RefactoringPlanner:
    """Planificador de refactorización de código"""
    
    def __init__(self):
        self.analyzer = ASTAnalyzer() if TOOLS_AVAILABLE else None
        self.editor = SmartEditor() if TOOLS_AVAILABLE else None
    
    def plan_refactoring(self, file_path: str, refactoring_type: str) -> Dict:
        """
        Planifica una refactorización
        
        Tipos soportados:
        - extract_method: Extraer método
        - rename_symbol: Renombrar símbolo
        - remove_duplication: Eliminar código duplicado
        - optimize_imports: Optimizar imports
        - add_type_hints: Agregar type hints
        """
        if not Path(file_path).exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        analysis = self.analyzer.analyze_file(file_path) if self.analyzer else None
        
        if refactoring_type == "extract_method":
            return self._plan_extract_method(file_path, analysis)
        elif refactoring_type == "rename_symbol":
            return self._plan_rename_symbol(file_path, analysis)
        elif refactoring_type == "optimize_imports":
            return self._plan_optimize_imports(file_path, analysis)
        elif refactoring_type == "add_type_hints":
            return self._plan_add_type_hints(file_path, analysis)
        else:
            return {"success": False, "error": f"Unknown refactoring type: {refactoring_type}"}
    
    def _plan_extract_method(self, file_path: str, analysis: Any) -> Dict:
        """Planifica extracción de método"""
        if not analysis or not analysis.functions:
            return {"success": False, "error": "No functions found to extract"}
        
        # Buscar función más larga
        longest_func = max(analysis.functions, key=lambda f: f.line_end - f.line_start)
        
        plan = {
            "success": True,
            "refactoring": "extract_method",
            "target": longest_func.name,
            "steps": [
                {
                    "id": 1,
                    "action": "analyze_function",
                    "description": f"Analizar función {longest_func.name} ({longest_func.line_end - longest_func.line_start} líneas)",
                    "params": {"function": longest_func.name}
                },
                {
                    "id": 2,
                    "action": "identify_extractable_block",
                    "description": "Identificar bloque de código para extraer",
                    "params": {"file": file_path, "function": longest_func.name}
                },
                {
                    "id": 3,
                    "action": "create_new_function",
                    "description": "Crear nueva función con bloque extraído",
                    "params": {"file": file_path}
                },
                {
                    "id": 4,
                    "action": "replace_with_call",
                    "description": "Reemplazar bloque original con llamada a nueva función",
                    "params": {"file": file_path}
                },
                {
                    "id": 5,
                    "action": "verify_syntax",
                    "description": "Verificar que el código sigue siendo válido",
                    "params": {"file": file_path}
                }
            ],
            "estimated_complexity": "medium",
            "risks": ["Cambiar comportamiento si hay variables compartidas"]
        }
        
        return plan
    
    def _plan_rename_symbol(self, file_path: str, analysis: Any) -> Dict:
        """Planifica renombrado de símbolo"""
        # Encontrar símbolos candidatos
        candidates = []
        if analysis:
            for func in analysis.functions:
                candidates.append({"type": "function", "name": func.name, "line": func.line_start})
            for cls in analysis.classes:
                candidates.append({"type": "class", "name": cls.name, "line": cls.line_start})
        
        return {
            "success": True,
            "refactoring": "rename_symbol",
            "candidates": candidates[:5],
            "steps": [
                {"id": 1, "action": "find_all_references", "description": "Encontrar todas las referencias al símbolo"},
                {"id": 2, "action": "rename_definition", "description": "Renombrar definición"},
                {"id": 3, "action": "rename_references", "description": "Renombrar todas las referencias"},
                {"id": 4, "action": "verify_changes", "description": "Verificar que no quedaron referencias antiguas"}
            ]
        }
    
    def _plan_optimize_imports(self, file_path: str, analysis: Any) -> Dict:
        """Planifica optimización de imports"""
        if not analysis:
            return {"success": False, "error": "Could not analyze file"}
        
        # Identificar imports no usados
        unused = []
        used_names = set()
        
        for func in analysis.functions:
            used_names.update(func.calls)
        
        for imp in analysis.imports:
            if imp.module not in used_names and not any(n in used_names for n in imp.names):
                unused.append(imp.module)
        
        return {
            "success": True,
            "refactoring": "optimize_imports",
            "unused_imports": unused,
            "steps": [
                {"id": 1, "action": "remove_unused_imports", "description": f"Eliminar {len(unused)} imports no usados"},
                {"id": 2, "action": "sort_imports", "description": "Ordenar imports alfabéticamente"},
                {"id": 3, "action": "group_imports", "description": "Agrupar imports (stdlib, third-party, local)"},
                {"id": 4, "action": "verify_syntax", "description": "Verificar sintaxis válida"}
            ]
        }
    
    def _plan_add_type_hints(self, file_path: str, analysis: Any) -> Dict:
        """Planifica agregar type hints"""
        if not analysis:
            return {"success": False, "error": "Could not analyze file"}
        
        # Funciones sin type hints
        funcs_needing_hints = []
        for func in analysis.functions:
            if not any("->" in str(arg) for arg in [func.docstring or ""]):
                funcs_needing_hints.append(func.name)
        
        return {
            "success": True,
            "refactoring": "add_type_hints",
            "functions_to_update": funcs_needing_hints,
            "steps": [
                {"id": 1, "action": "analyze_function_signatures", "description": "Analizar firmas de funciones"},
                {"id": 2, "action": "infer_types", "description": "Inferir tipos de parámetros y retornos"},
                {"id": 3, "action": "add_type_annotations", "description": "Agregar anotaciones de tipo"},
                {"id": 4, "action": "verify_with_mypy", "description": "Verificar con mypy (si disponible)"}
            ]
        }


class CodeGenerator:
    """Generador de código Python"""
    
    def __init__(self):
        self.template_engine = TemplateEngine()
    
    def generate_function(self, name: str, description: str, 
                         parameters: List[Dict], returns: str) -> str:
        """Genera una función con docstring"""
        
        # Generar parámetros
        params_str = ", ".join([p["name"] for p in parameters])
        
        # Generar type hints
        params_with_types = []
        for p in parameters:
            param_str = p["name"]
            if p.get("type"):
                param_str += f": {p['type']}"
            if p.get("default"):
                param_str += f" = {p['default']}"
            params_with_types.append(param_str)
        
        params_with_types_str = ", ".join(params_with_types)
        return_type = f" -> {returns}" if returns else ""
        
        # Generar docstring
        docstring = f'"""\n{description}\n\nArgs:\n'
        for p in parameters:
            docstring += f'    {p["name"]}: {p.get("description", "No description")}\n'
        docstring += f'\nReturns:\n    {returns if returns else "None"}\n"""'
        
        # Generar función
        code = f"""def {name}({params_with_types_str}){return_type}:
    {docstring}
    
    # TODO: Implement function logic
    pass
"""
        
        return code
    
    def generate_class(self, name: str, description: str,
                      attributes: List[Dict], methods: List[Dict],
                      inherits: List[str] = None) -> str:
        """Genera una clase con métodos"""
        
        inheritance = f"({', '.join(inherits)})" if inherits else ""
        
        # Atributos __init__
        init_params = ["self"]
        init_body = []
        for attr in attributes:
            param = attr["name"]
            if attr.get("type"):
                param += f": {attr['type']}"
            if attr.get("default"):
                param += f" = {attr['default']}"
                init_body.append(f"        self.{attr['name']} = {attr['name']}")
            else:
                init_params.append(param)
                init_body.append(f"        self.{attr['name']} = {attr['name']}")
        
        # Generar métodos
        methods_code = []
        for method in methods:
            method_code = self.generate_function(
                method["name"],
                method.get("description", ""),
                [{"name": "self"}] + method.get("parameters", []),
                method.get("returns", "None")
            )
            methods_code.append(method_code)
        
        # Ensamblar clase
        code = f'''class {name}{inheritance}:
    """{description}"""
    
    def __init__({', '.join(init_params)}):
{chr(10).join(init_body) if init_body else "        pass"}

'''
        code += "\n".join(methods_code)
        
        return code
    
    def generate_test(self, function_name: str, test_cases: List[Dict]) -> str:
        """Genera tests unitarios"""
        
        code = f"""import unittest


class Test{function_name.title()}(unittest.TestCase):
    \"\"\"Tests for {function_name} function\"\"\"
    
"""
        
        for i, test in enumerate(test_cases, 1):
            code += f'''    def test_{function_name}_{test.get("name", f"case_{i}")}(self):
        \"\"\"{test.get("description", "Test case")}\"\"\"
        # Arrange
        {test.get("setup", "pass")}
        
        # Act
        result = {function_name}({test.get("args", "")})
        
        # Assert
        self.assertEqual(result, {test.get("expected", "None")})

'''
        
        code += """
if __name__ == "__main__":
    unittest.main()
"""
        
        return code


class TemplateEngine:
    """Motor de templates simple"""
    
    def render(self, template: str, context: Dict) -> str:
        """Renderiza un template con variables"""
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{{ {key} }}}}", str(value))
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


# Funciones de conveniencia
def debug_error(error_message: str, file_path: str = "", stack_trace: str = "") -> Dict:
    """Debuggea un error y devuelve resultado"""
    debugger = DebugReasoner()
    result = debugger.analyze_error(error_message, stack_trace, file_path)
    
    return {
        "success": True,
        "error": result.error,
        "root_cause": result.root_cause,
        "hypotheses_count": len(result.hypotheses),
        "top_hypothesis": result.hypotheses[0].description if result.hypotheses else None,
        "suggested_fix": result.solution,
        "confidence": result.hypotheses[0].confidence if result.hypotheses else 0.0
    }


def plan_refactoring(file_path: str, refactoring_type: str) -> Dict:
    """Planifica una refactorización"""
    planner = RefactoringPlanner()
    return planner.plan_refactoring(file_path, refactoring_type)


def generate_code(code_type: str, **kwargs) -> Dict:
    """Genera código"""
    generator = CodeGenerator()
    
    if code_type == "function":
        code = generator.generate_function(**kwargs)
    elif code_type == "class":
        code = generator.generate_class(**kwargs)
    elif code_type == "test":
        code = generator.generate_test(**kwargs)
    else:
        return {"success": False, "error": f"Unknown code type: {code_type}"}
    
    return {
        "success": True,
        "code": code,
        "lines": len(code.split('\n')),
        "type": code_type
    }


__all__ = [
    'DebugReasoner',
    'RefactoringPlanner', 
    'CodeGenerator',
    'Hypothesis',
    'DebugResult',
    'debug_error',
    'plan_refactoring',
    'generate_code'
]


if __name__ == "__main__":
    # Test
    print("Testing reasoning module...")
    
    # Test debug
    debugger = DebugReasoner()
    result = debugger.analyze_error("NameError: name 'undefined_var' is not defined")
    print(f"\nDebug result:")
    print(f"  Root cause: {result.root_cause}")
    print(f"  Hypotheses: {len(result.hypotheses)}")
    
    # Test generator
    generator = CodeGenerator()
    code = generator.generate_function(
        "calculate_area",
        "Calculate the area of a rectangle",
        [{"name": "width", "type": "float"}, {"name": "height", "type": "float"}],
        "float"
    )
    print(f"\nGenerated function:\n{code}")
