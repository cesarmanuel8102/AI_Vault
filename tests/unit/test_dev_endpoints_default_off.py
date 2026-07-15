"""
FASE-0-SEGURIDAD / Patch 0C test
=================================
Verifica:
1. BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS por defecto = False (sin variable de entorno).
2. Solo se activa con valores truthy estrictos {"1","true","yes","on"}.
3. /dev y /godmode devuelven HTTP 403 cuando esta deshabilitado (no JSON 200).
"""
import importlib
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TMP = _ROOT / "tmp_agent"
for p in (_ROOT, _TMP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _reload_config(env_value):
    """Reload config.py con un valor de env especifico."""
    if env_value is None:
        os.environ.pop("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", None)
    else:
        os.environ["BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS"] = env_value
    if "brain_v9.config" in sys.modules:
        return importlib.reload(sys.modules["brain_v9.config"])
    return importlib.import_module("brain_v9.config")


def test_default_off_when_unset():
    cfg = _reload_config(None)
    assert cfg.BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is False, "Default debe ser False sin env var"


def test_off_for_arbitrary_values():
    for val in ["", "0", "false", "no", "off", "garbage", "FOO"]:
        cfg = _reload_config(val)
        assert cfg.BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is False, f"Valor {val!r} debe quedar OFF"


def test_on_for_strict_truthy():
    for val in ["1", "true", "TRUE", "yes", "YES", "on", "ON"]:
        cfg = _reload_config(val)
        assert cfg.BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is True, f"Valor {val!r} debe activar ON"


def test_dev_endpoint_returns_403_when_disabled():
    """Verifica que el codigo de /dev y /godmode levanta HTTPException(403)."""
    routes_path = _TMP / "brain_v9" / "routes" / "chat_session_lifecycle_routes.py"
    src = routes_path.read_text(encoding="utf-8", errors="ignore")
    # Ambos endpoints deben usar HTTPException con status_code=403, no return JSON.
    assert src.count("status_code=403") >= 2, "Faltan respuestas HTTP 403 en /dev y /godmode"
    # Asegura que no haya regresiones al patron antiguo de JSON success=False
    assert 'Endpoint /dev deshabilitado por seguridad",\n            "enable"' not in src
    assert 'Endpoint /godmode deshabilitado por seguridad",\n            "enable"' not in src


def _find_unsafe_gate_blocks_ast():
    """Busca via AST los gates unsafe-dev post-split en /dev y /godmode."""
    import ast
    routes_path = _TMP / "brain_v9" / "routes" / "chat_session_lifecycle_routes.py"
    src = routes_path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(src)

    targets = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in {"dev_mode_endpoint", "godmode_endpoint"}:
            continue
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.If):
                continue
            t = stmt.test
            # match legacy: if not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS:
            legacy_global_gate = (
                isinstance(t, ast.UnaryOp)
                and isinstance(t.op, ast.Not)
                and isinstance(t.operand, ast.Name)
                and t.operand.id == "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS"
            )
            # match split router: if not runtime["unsafe_dev_endpoints_enabled"]:
            runtime_mapping_gate = (
                isinstance(t, ast.UnaryOp)
                and isinstance(t.op, ast.Not)
                and isinstance(t.operand, ast.Subscript)
                and isinstance(t.operand.value, ast.Name)
                and t.operand.value.id == "runtime"
                and isinstance(t.operand.slice, ast.Constant)
                and t.operand.slice.value == "unsafe_dev_endpoints_enabled"
            )
            if (
                legacy_global_gate
                or runtime_mapping_gate
            ):
                targets.append((node.name, stmt))
    return targets


def test_no_dead_code_return_before_raise_in_unsafe_gate():
    """Patch 0C hardening: el bloque `if not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS:` NO debe
    contener `return ...` antes de `raise HTTPException(...)`. El return haria al
    raise inalcanzable y el endpoint seguiria devolviendo JSON 200."""
    import ast

    targets = _find_unsafe_gate_blocks_ast()
    assert len(targets) >= 2, (
        f"Se esperaban al menos 2 gates (dev + godmode), encontrados: {len(targets)}"
    )

    for func_name, if_node in targets:
        body = if_node.body
        # 1. Debe existir al menos un `raise HTTPException(...)` con status_code=403.
        raise_403 = False
        for stmt in body:
            if isinstance(stmt, ast.Raise) and isinstance(stmt.exc, ast.Call):
                fn = stmt.exc.func
                fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if fname == "HTTPException":
                    for kw in stmt.exc.keywords:
                        if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and kw.value.value == 403:
                            raise_403 = True
                            break
        assert raise_403, f"{func_name}: falta raise HTTPException(status_code=403)"

        # 2. NO debe haber `return` antes de cualquier raise dentro del bloque.
        for i, stmt in enumerate(body):
            if isinstance(stmt, ast.Return):
                tail = body[i + 1:]
                has_raise_after = any(isinstance(s, ast.Raise) for s in tail)
                assert not has_raise_after, (
                    f"{func_name}: detectado codigo muerto -> 'return' antes de 'raise' "
                    "dentro del bloque if not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS"
                )

        # 3. Si existe un raise, no puede haber Return en el mismo bloque (forma estricta).
        has_raise = any(isinstance(s, ast.Raise) for s in body)
        if has_raise:
            for stmt in body:
                assert not isinstance(stmt, ast.Return), (
                    f"{func_name}: el gate usa raise HTTPException pero tambien return JSON; "
                    "elimina el return para evitar regresion HTTP 200."
                )


def test_at_least_two_raise_403_in_dev_godmode_route_source():
    routes_path = _TMP / "brain_v9" / "routes" / "chat_session_lifecycle_routes.py"
    src = routes_path.read_text(encoding="utf-8", errors="ignore")
    # Patron tolerante a indentacion: raise HTTPException(...status_code=403...)
    import re
    matches = re.findall(r"raise\s+HTTPException\s*\([^)]*status_code\s*=\s*403", src, re.DOTALL)
    assert len(matches) >= 2, f"Se esperaban >=2 raise HTTPException(403); encontrados: {len(matches)}"


if __name__ == "__main__":
    test_default_off_when_unset()
    test_off_for_arbitrary_values()
    test_on_for_strict_truthy()
    test_dev_endpoint_returns_403_when_disabled()
    test_no_dead_code_return_before_raise_in_unsafe_gate()
    test_at_least_two_raise_403_in_dev_godmode_route_source()
    print("OK: test_dev_endpoints_default_off")
