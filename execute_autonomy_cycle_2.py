#!/usr/bin/env python
"""
EJECUTAR SIGUIENTE CICLO DE AUTONOMÍA - ITERATION 2
improve_expectancy_or_reduce_penalties
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def execute_autonomy_cycle():
    print("\n" + "=" * 80)
    print(" " * 15 + "🤖 BRAIN V9 - AUTONOMY CYCLE ITERATION 2")
    print("=" * 80)

    # Verificar estado actual antes de ejecutar
    state_dir = Path("tmp_agent/state")
    utility_path = state_dir / "utility_u_latest.json"

    if utility_path.exists():
        utility = json.loads(utility_path.read_text(encoding="utf-8"))
        current_u = utility.get("u_proxy_score", "N/A")
        blockers = utility.get("promotion_gate", {}).get("blockers", [])

        print(f"\n📊 ESTADO ACTUAL ANTES DE EJECUTAR:")
        print(f"   Utility U: {current_u}")
        print(f"   Blockers activos: {', '.join(blockers) if blockers else 'NINGUNO'}")
        print(f"   Sample Quality: {utility.get('strategy_context', {}).get('top_strategy', {}).get('sample_quality', 'N/A')}")

    print(f"\n🎯 EJECUTANDO: improve_expectancy_or_reduce_penalties (ITERATION 2)")
    print(f"   Objetivo: Continuar mejorando u de {current_u} → positivo")
    print(f"   Estrategia: Evaluar alternativas para breakout vs reversion")
    print(f"   Método: Comparación de estrategias candidatas")

    # Ejecutar el script de autonomía
    try:
        result = subprocess.run([
            sys.executable, "execute_autonomy_action.py"
        ], capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print(f"\n✅ CICLO DE AUTONOMÍA COMPLETADO EXITOSAMENTE")
            print(f"   Exit Code: {result.returncode}")

            # Mostrar output relevante
            output_lines = result.stdout.strip().split('\n')
            for line in output_lines[-10:]:  # Últimas 10 líneas
                if line.strip():
                    print(f"   {line}")

            # Verificar si se creó un nuevo job
            jobs_dir = state_dir / "autonomy_action_jobs"
            if jobs_dir.exists():
                jobs = sorted([d for d in jobs_dir.iterdir() if d.is_dir()])[-1:]  # Último job
                if jobs:
                    job_dir = jobs[0]
                    result_file = job_dir / "result.json"
                    if result_file.exists():
                        job_result = json.loads(result_file.read_text(encoding="utf-8"))
                        action = job_result.get("action", "unknown")
                        status = job_result.get("status", "unknown")

                        print(f"\n📋 RESULTADO DEL JOB:")
                        print(f"   Acción: {action}")
                        print(f"   Status: {status}")

                        if "details" in job_result:
                            details = job_result["details"]
                            if "comparison_context" in details:
                                winner = details["comparison_context"].get("winner", "N/A")
                                confidence = details["comparison_context"].get("confidence", "N/A")
                                print(f"   Ganador: {winner}")
                                print(f"   Confianza: {confidence}")

            return True

        else:
            print(f"\n❌ ERROR EN CICLO DE AUTONOMÍA")
            print(f"   Exit Code: {result.returncode}")
            print(f"   Error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n⏰ TIMEOUT: El ciclo de autonomía tomó más de 60 segundos")
        return False
    except Exception as e:
        print(f"\n💥 ERROR EJECUTANDO AUTONOMÍA: {e}")
        return False

def check_post_execution_state():
    """Verificar estado después de la ejecución"""
    print(f"\n🔍 VERIFICANDO ESTADO POST-EJECUCIÓN...")

    state_dir = Path("tmp_agent/state")
    utility_path = state_dir / "utility_u_latest.json"

    if utility_path.exists():
        utility = json.loads(utility_path.read_text(encoding="utf-8"))
        new_u = utility.get("u_proxy_score", "N/A")
        new_blockers = utility.get("promotion_gate", {}).get("blockers", [])

        print(f"   Utility U: {new_u}")
        print(f"   Blockers: {', '.join(new_blockers) if new_blockers else 'NINGUNO'}")

        # Comparar con estado anterior (asumiendo que se guardó)
        if hasattr(check_post_execution_state, 'previous_u'):
            improvement = float(new_u) - float(check_post_execution_state.previous_u) if new_u != "N/A" and check_post_execution_state.previous_u != "N/A" else 0
            print(f"   Mejora: {improvement:+.4f}")

        # Guardar para próxima comparación
        check_post_execution_state.previous_u = new_u

        return new_u, new_blockers
    else:
        print("   ⚠️  No se pudo leer utility_u_latest.json")
        return None, None

if __name__ == "__main__":
    success = execute_autonomy_cycle()

    if success:
        new_u, new_blockers = check_post_execution_state()

        print(f"\n" + "=" * 80)
        print(" " * 20 + "✅ AUTONOMY CYCLE 2 - COMPLETED")
        print("=" * 80)

        if new_u and float(new_u) > -0.0756:
            print(f"🎉 ¡MEJORA LOGRADA! U mejoró de -0.0756 → {new_u}")
        elif new_u:
            print(f"📈 Progreso continuo. U actual: {new_u}")
        else:
            print("📊 Estado post-ejecución no disponible")

        print(f"\n📋 PRÓXIMOS PASOS RECOMENDADOS:")
        print(f"   • Monitorear evolución de U en próximos ciclos")
        print(f"   • Continuar con improve_expectancy_or_reduce_penalties si U < 0")
        print(f"   • Preparar para promoción cuando U > 0")

    else:
        print(f"\n" + "=" * 80)
        print(" " * 20 + "❌ AUTONOMY CYCLE 2 - FAILED")
        print("=" * 80)
        print("   Revisar logs de error y reintentar")