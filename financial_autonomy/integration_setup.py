from pathlib import Path
import os


def integrate_with_brain_server(vault_path: str | Path | None = None, *, dry_run: bool = True) -> bool:
    """Prepare a financial-autonomy integration patch plan for Brain Server.

    Defaults to dry-run to avoid mutating runtime entrypoints accidentally.
    """
    root = Path(vault_path or os.getenv("BRAIN_BASE_PATH", Path(__file__).resolve().parents[1]))
    brain_files = list(root.rglob("brain_server*.py"))
    if not brain_files:
        print("No se encontro brain_server.py")
        return False

    latest_brain = max(brain_files, key=lambda x: x.stat().st_mtime)
    print(f"Integracion candidata: {latest_brain.name}")
    content = latest_brain.read_text(encoding="utf-8")
    if "financial_autonomy" in content:
        print("Integracion financiera ya existe")
        return True
    if dry_run:
        print("Dry-run: no se modifico Brain Server")
        return True

    integration_import = "\n\n# === FINANCIAL AUTONOMY INTEGRATION ===\nfrom financial_autonomy.api.financial_endpoints import router as financial_autonomy_router\n"
    lines = content.split("\n")
    last_import_index = 0
    for i, line in enumerate(lines):
        if line.startswith("import") or line.startswith("from"):
            last_import_index = i
    lines.insert(last_import_index + 1, integration_import.strip())
    lines.append("\napp.include_router(financial_autonomy_router)")
    latest_brain.write_text("\n".join(lines), encoding="utf-8")
    print("Integracion financiera anadida a Brain Server")
    return True


if __name__ == "__main__":
    integrate_with_brain_server(dry_run=True)
