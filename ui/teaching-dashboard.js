/**
 * TEACHING-DASHBOARD.JS
 * Widgets de Teaching Loop y Meta-Cognición para Brain Chat V9
 * 
 * Instrucciones de uso:
 * 1. Incluir este script en index.html: <script src="teaching-dashboard.js"></script>
 * 2. Los widgets se integran automáticamente
 * 3. Comunicación vía API endpoints /teaching/*
 */

(function() {
  'use strict';

  // ─── CONFIGURACIÓN ─────────────────────────────────────────────────────────
  const CONFIG = {
    apiBaseUrl: window.location.origin.includes('localhost') 
      ? 'http://localhost:8010' 
      : window.location.origin,
    refreshInterval: 5000, // 5 segundos
    maxMessages: 100,
  };

  // ─── ESTADO GLOBAL ───────────────────────────────────────────────────────────
  const state = {
    currentSession: null,
    currentPhase: 'ingesta',
    messages: [],
    metacognition: {},
    metrics: {},
    isTeachingMode: false,
  };

  // ─── UTILIDADES ──────────────────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);
  
  const api = {
    async get(path) {
      const res = await fetch(`${CONFIG.apiBaseUrl}/teaching${path}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    async post(path, body) {
      const res = await fetch(`${CONFIG.apiBaseUrl}/teaching${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
  };

  const formatPercent = (val) => `${(val * 100).toFixed(1)}%`;
  const formatTime = (iso) => new Date(iso).toLocaleTimeString();

  // ─── COMPONENTES UI ──────────────────────────────────────────────────────────
  
  // Gauge circular para métricas
  function createGauge(value, label, color) {
    const pct = Math.max(0, Math.min(1, value)) * 100;
    return `
      <div class="teaching-gauge" style="text-align:center;padding:16px;">
        <div style="position:relative;width:80px;height:80px;margin:0 auto;">
          <svg viewBox="0 0 36 36" style="width:100%;height:100%;transform:rotate(-90deg);">
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" 
                  fill="none" stroke="var(--surface2)" stroke-width="3"/>
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" 
                  fill="none" stroke="${color}" stroke-width="3"
                  stroke-dasharray="${pct}, 100" style="transition:stroke-dasharray 0.5s;"/>
          </svg>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:16px;font-weight:600;">
            ${Math.round(pct)}%
          </div>
        </div>
        <div style="margin-top:8px;font-size:12px;color:var(--text2);">${label}</div>
      </div>
    `;
  }

  // Barra de progreso
  function createProgressBar(value, label, color = 'var(--accent)') {
    const pct = Math.max(0, Math.min(100, value));
    return `
      <div style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:12px;">
          <span style="color:var(--text2);">${label}</span>
          <span style="color:var(--text);">${pct.toFixed(1)}%</span>
        </div>
        <div style="height:6px;background:var(--surface2);border-radius:3px;overflow:hidden;">
          <div style="height:100%;width:${pct}%;background:${color};border-radius:3px;transition:width 0.5s;"></div>
        </div>
      </div>
    `;
  }

  // Card de información
  function createInfoCard(title, value, subtitle = '', type = 'neutral') {
    const colors = {
      neutral: 'var(--text)',
      success: 'var(--green)',
      warning: 'var(--amber)',
      error: 'var(--red)',
    };
    return `
      <div class="card" style="padding:16px;">
        <div class="label" style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--text2);margin-bottom:8px;">
          ${title}
        </div>
        <div class="value" style="font-size:24px;font-weight:600;color:${colors[type]};">
          ${value}
        </div>
        ${subtitle ? `<div class="sub" style="font-size:12px;color:var(--text2);margin-top:4px;">${subtitle}</div>` : ''}
      </div>
    `;
  }

  // ─── PANELES ─────────────────────────────────────────────────────────────────

  // Panel de Meta-Cognición
  function renderMetacognitionPanel(data) {
    const metrics = data.metacognition_metrics || {};
    const caps = data.capabilities_summary || {};
    const gaps = data.knowledge_gaps || {};
    
    return `
      <div style="padding:20px;overflow-y:auto;height:100%;">
        <h3 style="margin-bottom:16px;color:var(--text2);font-size:14px;text-transform:uppercase;">
          🧠 Estado de Consciencia
        </h3>
        
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:16px;margin-bottom:24px;">
          ${createGauge(metrics.self_awareness_depth || 0, 'Autoconocimiento', 'var(--accent)')}
          ${createGauge(metrics.uncertainty_calibration || 0, 'Calibración', 'var(--green)')}
          ${createGauge(metrics.prediction_accuracy || 0, 'Precisión', 'var(--amber)')}
          ${createGauge(metrics.learning_rate || 0, 'Aprendizaje', 'var(--accent2)')}
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px;">
          ${createInfoCard('Modo Resiliencia', data.resilience_mode || 'unknown', `Stress: ${formatPercent(data.stress_level || 0)}`, 
            data.stress_level > 0.6 ? 'error' : data.stress_level > 0.3 ? 'warning' : 'success')}
          ${createInfoCard('Riesgo Unknowns', formatPercent(data.unknown_unknowns_risk || 0), 
            'Brechas no identificadas', data.unknown_unknowns_risk > 0.5 ? 'warning' : 'neutral')}
          ${createInfoCard('Capacidades', `${caps.reliable || 0}/${caps.total || 0}`, 
            `${caps.unreliable || 0} no fiables`, caps.reliable > caps.unreliable ? 'success' : 'warning')}
          ${createInfoCard('Brechas', gaps.open || 0, 
            `${gaps.in_progress || 0} en progreso`, gaps.open > 5 ? 'warning' : 'neutral')}
        </div>

        <h4 style="margin-bottom:12px;color:var(--text2);font-size:13px;">⚠️ Brechas de Conocimiento Críticas</h4>
        <div style="background:var(--surface);border-radius:8px;padding:12px;border:1px solid var(--border);">
          ${(data.knowledge_gaps?.high_impact || 0) > 0 ? `
            <div style="color:var(--amber);font-size:13px;margin-bottom:8px;">
              ${gaps.high_impact} brechas de alto impacto identificadas
            </div>
          ` : '<div style="color:var(--green);font-size:13px;">✓ No hay brechas críticas</div>'}
        </div>
      </div>
    `;
  }

  // Panel de Teaching Loop
  function renderTeachingPanel(data) {
    const session = data.teaching_session;
    if (!session) {
      return `
        <div style="padding:40px;text-align:center;">
          <div style="font-size:48px;margin-bottom:16px;">🎓</div>
          <h3 style="margin-bottom:12px;">Modo Teaching Inactivo</h3>
          <p style="color:var(--text2);margin-bottom:24px;">
            Inicia una sesión de aprendizaje para comenzar el ciclo de enseñanza
          </p>
          <button onclick="teachingDashboard.startSession()" 
                  style="background:var(--accent);border:none;color:#fff;padding:12px 24px;border-radius:8px;cursor:pointer;font-size:14px;">
            Iniciar Sesión
          </button>
        </div>
      `;
    }

    const phaseColors = {
      ingesta: 'var(--accent)',
      prueba: 'var(--amber)',
      resultados: 'var(--green)',
      evaluacion: 'var(--accent2)',
      mejora: 'var(--red)',
      checkpoint: 'var(--green)',
    };

    return `
      <div style="padding:20px;overflow-y:auto;height:100%;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
          <h3 style="color:var(--text2);font-size:14px;text-transform:uppercase;">
            🎓 Sesión: ${session.session_id?.split('_')[1] || 'Active'}
          </h3>
          <span style="background:${phaseColors[session.phase] || 'var(--surface)'};color:#fff;padding:4px 12px;border-radius:12px;font-size:11px;text-transform:uppercase;">
            Fase: ${session.phase}
          </span>
        </div>

        ${createProgressBar(session.progress_percentage || 0, 'Progreso de Objetivos', 'var(--accent)')}
        
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin:24px 0;">
          ${createInfoCard('Objetivos', `${session.objectives_completed || 0}/${session.objectives_total || 0}`, 
            'Completados', session.objectives_completed >= session.objectives_total ? 'success' : 'neutral')}
          ${createInfoCard('Tasa Éxito', formatPercent(session.success_rate || 0), 
            `${session.successes || 0}/${session.attempts || 0} intentos`, 
            (session.success_rate || 0) > 0.7 ? 'success' : (session.success_rate || 0) > 0.4 ? 'warning' : 'error')}
          ${createInfoCard('Intentos', session.attempts || 0, 
            `${session.failures || 0} fallos`, session.failures > session.successes ? 'error' : 'neutral')}
          ${session.can_rollback ? createInfoCard('Rollback', 'Disponible', 'Punto de recuperación activo', 'success') : ''}
        </div>

        ${session.validation_pending ? `
          <div style="background:var(--amber);background-opacity:0.1;border:1px solid var(--amber);border-radius:8px;padding:16px;margin:16px 0;">
            <div style="font-weight:600;margin-bottom:8px;">⏳ Validación Pendiente</div>
            <p style="font-size:13px;margin-bottom:12px;">Checkpoint creado. Esperando aprobación del mentor.</p>
            <div style="display:flex;gap:8px;">
              <button onclick="teachingDashboard.approveCheckpoint('${session.session_id}')" 
                      style="background:var(--green);border:none;color:#fff;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
                ✅ Aprobar
              </button>
              <button onclick="teachingDashboard.rollbackSession()" 
                      style="background:var(--red);border:none;color:#fff;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
                ⏮️ Rollback
              </button>
            </div>
          </div>
        ` : ''}

        <h4 style="margin:24px 0 12px;color:var(--text2);font-size:13px;">Acciones Rápidas</h4>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">
          <button onclick="teachingDashboard.nextPhase('ingesta')" 
                  style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
            📥 Ingesta
          </button>
          <button onclick="teachingDashboard.nextPhase('prueba')" 
                  style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
            📝 Prueba
          </button>
          <button onclick="teachingDashboard.nextPhase('evaluacion')" 
                  style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
            📊 Evaluación
          </button>
          <button onclick="teachingDashboard.createCheckpoint()" 
                  style="background:var(--accent);border:none;color:#fff;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
            💾 Checkpoint
          </button>
          <button onclick="teachingDashboard.endSession()" 
                  style="background:var(--surface2);border:1px solid var(--red);color:var(--red);padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">
            🛑 Finalizar
          </button>
        </div>
      </div>
    `;
  }

  // Panel de Chat Teaching
  function renderTeachingChat() {
    return `
      <div style="flex:1;display:flex;flex-direction:column;height:100%;">
        <div id="teaching-messages" style="flex:1;overflow-y:auto;padding:20px;background:var(--bg);">
          ${state.messages.length === 0 ? `
            <div style="text-align:center;padding:40px;color:var(--text2);">
              <div style="font-size:32px;margin-bottom:12px;">💬</div>
              <p>Los mensajes del Teaching Loop aparecerán aquí</p>
              <p style="font-size:12px;margin-top:8px;">Usa los comandos /teaching en el chat principal</p>
            </div>
          ` : state.messages.map(msg => `
            <div class="msg ${msg.role}" style="margin-bottom:12px;display:flex;gap:12px;${msg.role === 'user' ? 'flex-direction:row-reverse;' : ''}">
              <div class="avatar" style="width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;background:${msg.role === 'user' ? 'var(--accent)' : msg.role === 'mentor' ? 'var(--green)' : 'var(--surface2)'};color:${msg.role === 'system' ? 'var(--amber)' : '#fff'};">
                ${msg.role === 'user' ? 'U' : msg.role === 'mentor' ? 'M' : 'B'}
              </div>
              <div class="bubble" style="padding:12px 16px;border-radius:12px;background:${msg.role === 'user' ? 'var(--accent)' : 'var(--surface)'};color:${msg.role === 'user' ? '#fff' : 'var(--text)'};border:${msg.role === 'user' ? 'none' : '1px solid var(--border)'};max-width:600px;line-height:1.5;${msg.role === 'user' ? 'border-radius:12px 4px 12px 12px;' : 'border-radius:4px 12px 12px 12px;'};">
                ${msg.content.replace(/\n/g, '<br>')}
              </div>
            </div>
          `).join('')}
        </div>
        
        <div style="padding:16px 20px;background:var(--surface);border-top:1px solid var(--border);display:flex;gap:10px;">
          <input type="text" id="teaching-input" placeholder="Mensaje al sistema de teaching..." 
                 style="flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;color:var(--text);font-size:14px;"
                 onkeypress="if(event.key==='Enter') teachingDashboard.sendTeachingMessage()">
          <button onclick="teachingDashboard.sendTeachingMessage()" 
                  style="background:var(--accent);border:none;color:#fff;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:14px;">
            Enviar
          </button>
        </div>
      </div>
    `;
  }

  // ─── INTEGRACIÓN CON DASHBOARD ──────────────────────────────────────────────

  // Crear tab de Teaching en el nav
  function createTeachingTab() {
    const nav = $('nav');
    if (!nav) return;
    
    // Verificar si ya existe
    if ($('button[onclick*="teaching"]')) return;
    
    const teachingBtn = document.createElement('button');
    teachingBtn.innerHTML = '🎓 Teaching';
    teachingBtn.setAttribute('onclick', "showPanel('teaching')");
    teachingBtn.id = 'nav-teaching';
    nav.appendChild(teachingBtn);
  }

  // Crear panel de Teaching
  function createTeachingPanel() {
    if ($('#panel-teaching')) return;
    
    const panel = document.createElement('div');
    panel.id = 'panel-teaching';
    panel.className = 'panel';
    panel.innerHTML = `
      <div style="display:flex;height:100%;">
        <div style="width:350px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;">
          <div style="padding:16px;border-bottom:1px solid var(--border);background:var(--surface);">
            <h3 style="font-size:14px;color:var(--text2);text-transform:uppercase;">Sesión Actual</h3>
          </div>
          <div id="teaching-session-panel" style="flex:1;overflow-y:auto;">
            Cargando...
          </div>
        </div>
        
        <div style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
          <div style="padding:16px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;justify-content:space-between;align-items:center;">
            <h3 style="font-size:14px;color:var(--text2);text-transform:uppercase;">Conversación Teaching</h3>
            <div style="display:flex;gap:8px;">
              <button onclick="teachingDashboard.refreshData()" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px;">
                ↻ Actualizar
              </button>
            </div>
          </div>
          <div id="teaching-chat-container" style="flex:1;overflow:hidden;">
            ${renderTeachingChat()}
          </div>
        </div>
        
        <div style="width:300px;border-left:1px solid var(--border);overflow-y:auto;background:var(--surface);">
          <div id="metacognition-panel">
            Cargando meta-cognición...
          </div>
        </div>
      </div>
    `;
    
    // Insertar después del último panel
    const lastPanel = $$('.panel')[$$('.panel').length - 1];
    if (lastPanel) {
      lastPanel.parentNode.insertBefore(panel, lastPanel.nextSibling);
    }
  }

  // ─── ACCIONES ─────────────────────────────────────────────────────────────────

  const actions = {
    async startSession() {
      const topic = prompt('Tema de la sesión de enseñanza:');
      if (!topic) return;
      
      try {
        const result = await api.post('/session/start', { topic });
        if (result.session_id) {
          alert(`Sesión iniciada: ${result.session_id}`);
          await this.refreshData();
        }
      } catch (e) {
        alert('Error iniciando sesión: ' + e.message);
      }
    },

    async nextPhase(phase) {
      try {
        const body = { phase };
        if (phase === 'ingesta') {
          const content = prompt('Contenido a ingestar:');
          if (!content) return;
          body.content = content;
        }
        
        await api.post('/session/phase', body);
        await this.refreshData();
      } catch (e) {
        alert('Error cambiando fase: ' + e.message);
      }
    },

    async createCheckpoint() {
      try {
        await api.post('/session/checkpoint', {});
        alert('Checkpoint creado. Esperando validación.');
        await this.refreshData();
      } catch (e) {
        alert('Error creando checkpoint: ' + e.message);
      }
    },

    async approveCheckpoint(checkpointId) {
      const approver = prompt('Tu nombre (aprobador):');
      if (!approver) return;
      
      try {
        await api.post('/session/checkpoint/approve', {
          checkpoint_id: checkpointId,
          approver: approver
        });
        alert('Checkpoint aprobado');
        await this.refreshData();
      } catch (e) {
        alert('Error aprobando checkpoint: ' + e.message);
      }
    },

    async rollbackSession() {
      if (!confirm('¿Estás seguro de hacer rollback? Se perderá el progreso desde el último checkpoint.')) return;
      
      try {
        await api.post('/session/rollback', {});
        alert('Rollback ejecutado');
        await this.refreshData();
      } catch (e) {
        alert('Error en rollback: ' + e.message);
      }
    },

    async endSession() {
      if (!confirm('¿Finalizar sesión actual?')) return;
      
      try {
        await api.post('/session/end', {});
        alert('Sesión finalizada');
        await this.refreshData();
      } catch (e) {
        alert('Error finalizando: ' + e.message);
      }
    },

    async sendTeachingMessage() {
      const input = $('#teaching-input');
      const message = input?.value?.trim();
      if (!message) return;
      
      // Agregar a mensajes locales
      state.messages.push({
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
      });
      
      // Limpiar input
      input.value = '';
      this.updateChatUI();
      
      // Procesar comando
      if (message.startsWith('/')) {
        await this.processCommand(message);
      } else {
        // Enviar a fase actual
        const teaching = $('#teaching-session-panel');
        if (teaching?.textContent?.includes('ingesta')) {
          await this.nextPhase('ingesta');
        }
      }
    },

    async processCommand(cmd) {
      const parts = cmd.slice(1).split(' ');
      const command = parts[0];
      
      try {
        switch (command) {
          case 'validate':
            const passed = confirm('¿La prueba fue exitosa?');
            const score = parseFloat(prompt('Score (0-1):', '0.8') || '0.8');
            await api.post('/session/validate', {
              passed,
              score,
              feedback: passed ? 'Validación exitosa' : 'Necesita más práctica'
            });
            break;
            
          default:
            await api.post('/chat/command', {
              command,
              args: { message: parts.slice(1).join(' ') }
            });
        }
        await this.refreshData();
      } catch (e) {
        alert('Error procesando comando: ' + e.message);
      }
    },

    async refreshData() {
      try {
        // Obtener estado del dashboard
        const dashboardData = await api.get('/dashboard/state');
        state.currentSession = dashboardData.teaching?.teaching_session;
        state.metacognition = dashboardData.metacognition;
        state.metrics = dashboardData.teaching?.metacognition_metrics;
        
        // Obtener mensajes del chat
        const messagesData = await api.get('/dashboard/chat-messages');
        if (messagesData.messages) {
          state.messages = messagesData.messages;
        }
        
        this.updateUI();
      } catch (e) {
        console.error('Error refreshing data:', e);
        // Mostrar error en UI
        $('#teaching-session-panel').innerHTML = `
          <div style="padding:20px;color:var(--red);">
            Error cargando datos: ${e.message}<br>
            <button onclick="teachingDashboard.refreshData()" style="margin-top:12px;">Reintentar</button>
          </div>
        `;
      }
    },

    updateUI() {
      const sessionPanel = $('#teaching-session-panel');
      const metaPanel = $('#metacognition-panel');
      
      if (sessionPanel) {
        sessionPanel.innerHTML = renderTeachingPanel({ teaching_session: state.currentSession });
      }
      
      if (metaPanel) {
        metaPanel.innerHTML = renderMetacognitionPanel(state.metacognition || {});
      }
      
      this.updateChatUI();
    },

    updateChatUI() {
      const chatContainer = $('#teaching-chat-container');
      if (chatContainer) {
        chatContainer.innerHTML = renderTeachingChat();
      }
    },
  };

  // ─── INICIALIZACIÓN ────────────────────────────────────────────────────────────

  function init() {
    console.log('[Teaching Dashboard] Inicializando...');
    
    // Crear elementos UI
    createTeachingTab();
    createTeachingPanel();
    
    // Cargar datos iniciales
    actions.refreshData();
    
    // Auto-refresh cada 5 segundos
    setInterval(() => {
      if ($('#panel-teaching')?.classList?.contains('active')) {
        actions.refreshData();
      }
    }, CONFIG.refreshInterval);
    
    console.log('[Teaching Dashboard] Inicializado correctamente');
  }

  // Exponer API global
  window.teachingDashboard = actions;
  
  // Inicializar cuando DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
