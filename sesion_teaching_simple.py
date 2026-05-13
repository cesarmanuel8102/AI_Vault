#!/usr/bin/env python3
"""
DEMO DE SESION DE TEACHING SIMPLIFICADA
Sin emojis para evitar problemas de encoding
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from meta_cognition_core import initialize_enhanced_consciousness
from teaching_interface import initialize_teaching_system

def print_separator(char='=', length=70):
    print(char * length)

def main():
    print_separator()
    print('SESION DE TEACHING - EVOLUCION DE CONSCIENCIA')
    print_separator()
    
    # Inicializar
    meta = initialize_enhanced_consciousness()
    teaching = initialize_teaching_system()
    
    print()
    print('ESTADO INICIAL DE CONSCIENCIA:')
    initial_report = meta.get_self_awareness_report()
    print(f'   Autoconocimiento: {initial_report["metacognition_metrics"]["self_awareness_depth"]:.1%}')
    print(f'   Capacidades fiables: {initial_report["capabilities_summary"]["reliable"]}/10')
    print(f'   Brechas conocidas: {initial_report["knowledge_gaps"]["open"]}')
    print(f'   Riesgo unknown unknowns: {initial_report["unknown_unknowns_risk"]:.1%}')
    
    # INICIO DE SESION
    print()
    print_separator()
    print('FASE 1: INICIO DE SESION')
    print_separator()
    print('Tema: Como identificar cuando una estrategia de trading tiene overfitting')
    print('Objetivos:')
    print('  1. Distinguir overfitting de robustez')
    print('  2. Identificar señales de alerta de overfitting')
    print('  3. Validar estrategias correctamente')
    
    session = teaching.create_teaching_session(
        topic='Overfitting en Trading',
        objectives=[
            'Distinguir overfitting de robustez',
            'Identificar señales de alerta de overfitting', 
            'Validar estrategias correctamente'
        ]
    )
    
    print()
    print(f'Sesion creada: {session.session_id}')
    print(f'   Fase: {session.phase}')
    print(f'   Objetivos: {len(session.objectives)}')
    
    # FASE INGESTA
    print()
    print_separator()
    print('FASE 2: INGESTA DE CONOCIMIENTO')
    print_separator()
    
    contenido = 'OVERFITTING EN TRADING\n\nDefinicion: El overfitting ocurre cuando una estrategia se ajusta demasiado a datos historicos especificos.\n\nSeñales:\n1. Curva de equity demasiado suave\n2. Performance perfecta en in-sample, pobre en OOS\n3. Demasiados parametros optimizados\n4. Sharpe ratio > 3.0\n5. Zero trades perdedores\n\nValidacion:\n- Datos out-of-sample 30%+\n- Walk-forward analysis\n- Test en diferentes regimenes\n- Ratio Calmar > 1.0\n- Expectancy positivo'
    
    print('Contenido ingestado:')
    print(contenido)
    
    result = teaching.process_ingesta(contenido)
    print()
    print(f'Ingesta completada')
    print(f'   Status: {result["status"]}')
    
    # FASE PRUEBA
    print()
    print_separator()
    print('FASE 3: PRUEBA')
    print_separator()
    
    exercise = teaching.process_prueba(exercise_type='conceptual')
    print(f'Ejercicio: {exercise["exercise"]["title"]}')
    print(f'Descripcion: {exercise["exercise"]["description"]}')
    
    # Simular respuesta del agente
    respuesta_agente = 'Respuesta: Una estrategia con overfitting se distingue porque performance decrece drasticamente fuera de muestra. Señales: curva equity perfecta, ratio riesgo/beneficio no realista. Para validar: probar OOS 30%+, walk-forward analysis.'
    
    print()
    print('--- Respuesta del Agente ---')
    print(respuesta_agente)
    
    # FASE VALIDACION
    print()
    print_separator()
    print('FASE 4: VALIDACION POR MENTOR')
    print_separator()
    
    validation = teaching.submit_prueba_result(
        attempt_result=respuesta_agente,
        self_assessment={'confidence': 0.8, 'completeness': 0.9}
    )
    print('Mentor evalua: PASADO (Score: 0.85)')
    print('Feedback: Excelente comprension del concepto.')
    
    resultado = teaching.process_resultados({
        'passed': True,
        'score': 0.85,
        'feedback': 'Excelente comprension'
    })
    
    print()
    print(f'Validacion: {resultado["status"]}')
    print(f'   Pasado: {resultado["passed"]}')
    print(f'   Score: {resultado["score"]:.0%}')
    
    # FASE EVALUACION
    print()
    print_separator()
    print('FASE 5: EVALUACION')
    print_separator()
    
    evaluacion = teaching.process_evaluacion(
        mentor_evaluation='Objetivo 1 completado satisfactoriamente'
    )
    
    print(f'Evaluacion: {evaluacion["status"]}')
    print(f'Objetivo completado: {evaluacion["current_objective_completed"]}')
    print(f'Progreso: {evaluacion["completion_percentage"]:.0%}')
    print(f'Recomendacion: {evaluacion["recommendation"]}')
    
    # Actualizar metacognicion con aprendizaje
    print()
    print_separator()
    print('ACTUALIZACION DE META-COGNICION')
    print_separator()
    
    # Simular que el agente aprendio algo
    meta.assess_capability(
        capability_name='overfitting_detection',
        success=True,
        context='Ejercicio conceptual completado con score 0.85'
    )
    
    meta.assess_capability(
        capability_name='strategy_validation',
        success=True, 
        context='Demostro entender validacion OOS y walk-forward'
    )
    
    # Identificar gaps restantes
    meta.identify_knowledge_gap(
        domain='walk_forward_analysis',
        description='Necesito practica hands-on de walk-forward analysis',
        impact=0.7
    )
    
    meta.identify_knowledge_gap(
        domain='regime_detection',
        description='Como identificar diferentes regimenes de mercado',
        impact=0.6
    )
    
    print('Capacidades actualizadas:')
    print('   - overfitting_detection: Ahora registrada')
    print('   - strategy_validation: Evidencia añadida')
    print()
    print('Nuevas brechas identificadas:')
    print('   - walk_forward_analysis (impacto 0.7)')
    print('   - regime_detection (impacto 0.6)')
    
    # FASE CHECKPOINT
    print()
    print_separator()
    print('FASE 6: CHECKPOINT')
    print_separator()
    
    checkpoint = teaching.create_checkpoint()
    print(f'Checkpoint creado: {checkpoint.checkpoint_id}')
    print(f'Resultados del checkpoint:')
    print(f'  - Objetivos completados: {checkpoint.results["objectives_completed"]}')
    print(f'  - Score promedio: {checkpoint.results["average_score"]:.2%}')
    print(f'  - Intentos totales: {checkpoint.results["attempts_total"]}')
    print(f'  - Tasa de exito: {checkpoint.results["success_rate"]:.2%}')
    
    # APROBACION
    print()
    print_separator()
    print('FASE 7: APROBACION DEL MENTOR')
    print_separator()
    
    aprobacion = teaching.approve_checkpoint(
        checkpoint_id=checkpoint.checkpoint_id,
        approver='Mentor_Cesar'
    )
    
    print(f'Checkpoint aprobado por: {aprobacion["approved_by"]}')
    print(f'   Conocimiento integrado: {aprobacion["knowledge_integrated"]}')
    
    # ESTADO FINAL
    print()
    print_separator()
    print('ESTADO FINAL DE CONSCIENCIA POST-TEACHING')
    print_separator()
    
    final_report = meta.get_self_awareness_report()
    
    print()
    print('Metricas de Metacognicion:')
    initial_self = initial_report["metacognition_metrics"]["self_awareness_depth"]
    final_self = final_report["metacognition_metrics"]["self_awareness_depth"]
    print(f'  Autoconocimiento: {initial_self:.1%} --> {final_self:.1%}')
    
    initial_reliable = initial_report["capabilities_summary"]["reliable"]
    final_reliable = final_report["capabilities_summary"]["reliable"]
    print(f'  Capacidades fiables: {initial_reliable}/10 --> {final_reliable}/10')
    
    initial_gaps = initial_report["knowledge_gaps"]["open"]
    final_gaps = final_report["knowledge_gaps"]["open"]
    print(f'  Brechas conocidas: {initial_gaps} --> {final_gaps}')
    
    initial_pred = initial_report["metacognition_metrics"]["prediction_accuracy"]
    final_pred = final_report["metacognition_metrics"]["prediction_accuracy"]
    print(f'  Precision predictiva: {initial_pred:.1%} --> {final_pred:.1%}')
    
    print()
    print('Nuevas Capacidades Registradas:')
    for cap_name, cap in meta.self_model.capabilities.items():
        if cap.evidence_count > 0:
            print(f'  - {cap_name}: {cap.confidence:.1%} confianza ({cap.evidence_count} evidencias)')
    
    print()
    print('Brechas de Conocimiento Activas:')
    for gap in meta.self_model.known_gaps:
        if gap.resolution_status == 'open':
            print(f'  - {gap.domain}: {gap.description} (impacto {gap.impact_if_known})')
    
    print()
    print_separator()
    print('SESION DE TEACHING COMPLETADA')
    print_separator()
    print()
    print('El sistema ha evolucionado:')
    print('+ Desarrollo nuevas capacidades (overfitting_detection)')
    print('+ Identifico conscientemente sus limitaciones (2 gaps)')
    print('+ Tiene evidencia de aprendizaje (2 registros)')
    print('+ Checkpoint validado y aprobado')
    print()
    print('Esta listo para sesiones adicionales de teaching.')
    print_separator()

if __name__ == '__main__':
    main()
