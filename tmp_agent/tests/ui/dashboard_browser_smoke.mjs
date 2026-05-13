import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const edgePath = process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const dashboardUrl = process.env.DASHBOARD_URL || 'http://127.0.0.1:8090/dashboard';
const cdpPort = Number(process.env.CDP_PORT || 9223);
const userDataDir = mkdtempSync(path.join(tmpdir(), 'edge-dashboard-smoke-'));

let browser;
let websocket;
let closed = false;
const exceptions = [];
const consoleErrors = [];
const jsErrors = [];
const jsWarnings = [];

function cleanup() {
  if (closed) return;
  closed = true;
  try {
    websocket?.close();
  } catch {}
  try {
    browser?.kill('SIGTERM');
  } catch {}
  try {
    rmSync(userDataDir, { recursive: true, force: true });
  } catch {}
}

process.on('exit', cleanup);
process.on('SIGINT', () => {
  cleanup();
  process.exit(130);
});
process.on('SIGTERM', () => {
  cleanup();
  process.exit(143);
});

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForJson(url, retries = 60, delayMs = 250) {
  let lastError;
  for (let i = 0; i < retries; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return await response.json();
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await delay(delayMs);
  }
  throw lastError || new Error(`Could not fetch ${url}`);
}

async function connectToCdp(wsUrl) {
  return await new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    const pending = new Map();
    let messageId = 0;

    function send(method, params = {}) {
      return new Promise((resolveSend, rejectSend) => {
        messageId += 1;
        pending.set(messageId, { resolve: resolveSend, reject: rejectSend });
        ws.send(JSON.stringify({ id: messageId, method, params }));
      });
    }

    ws.addEventListener('message', event => {
      const payload = JSON.parse(event.data);
      if (payload.id && pending.has(payload.id)) {
        const handler = pending.get(payload.id);
        pending.delete(payload.id);
        if (payload.error) {
          handler.reject(new Error(payload.error.message || JSON.stringify(payload.error)));
        } else {
          handler.resolve(payload.result);
        }
        return;
      }
      if (payload.method === 'Runtime.exceptionThrown') {
        exceptions.push(payload.params);
      } else if (payload.method === 'Runtime.consoleAPICalled') {
        const level = payload.params?.type || 'log';
        const text = (payload.params?.args || []).map(arg => arg?.value ?? arg?.description ?? '').join(' ');
        if (level === 'error') {
          consoleErrors.push(text);
        }
      } else if (payload.method === 'Log.entryAdded') {
        const entry = payload.params?.entry || {};
        const level = String(entry.level || '').toLowerCase();
        const source = entry.url || entry.source || '';
        const text = `${entry.level}: ${entry.text || ''} ${source}`.trim();
        if (level === 'error') {
          jsErrors.push(text);
        } else if (level === 'warning') {
          jsWarnings.push(text);
        }
      }
    });

    ws.addEventListener('error', reject);
    ws.addEventListener('open', () => resolve({ ws, send }));
  });
}

async function main() {
  browser = spawn(edgePath, [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${userDataDir}`,
    'about:blank',
  ], {
    stdio: 'ignore',
    windowsHide: true,
  });

  const targets = await waitForJson(`http://127.0.0.1:${cdpPort}/json/list`);
  const pageTarget = targets.find(target => target.type === 'page') || targets[0];
  if (!pageTarget?.webSocketDebuggerUrl) {
    throw new Error('No page target available from Edge CDP.');
  }

  const cdp = await connectToCdp(pageTarget.webSocketDebuggerUrl);
  websocket = cdp.ws;
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');

  async function evaluateDashboard() {
    const evaluation = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const bodyText = document.body ? document.body.innerText : '';
        const stateErrors = Array.from(document.querySelectorAll('[data-state-kind="error"]'))
          .map(node => (node.innerText || '').trim())
          .filter(Boolean);
        return {
          title: document.title,
          hasOverviewKpis: !!document.querySelector('#overview-kpis'),
          hasDecisionStrip: !!document.querySelector('#overview-decision-strip'),
          hasStrategyKpis: !!document.querySelector('#strategy-kpis'),
          hasRefreshError: /Refresh error/i.test(bodyText),
          hasNotDefined: /is not defined/i.test(bodyText),
          stateErrors,
          bodySample: bodyText.slice(0, 3000),
        };
      })()`,
      returnByValue: true,
    });
    return evaluation.result?.value || {};
  }

  let result = {};
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    await cdp.send('Page.navigate', { url: dashboardUrl });
    await delay(9000);
    result = await evaluateDashboard();
    const hasTransientNetworkChanged = jsErrors.some(text => /ERR_NETWORK_CHANGED/i.test(text));
    const hasStateErrors = Array.isArray(result.stateErrors) && result.stateErrors.length > 0;
    if (attempt === 1 && (hasTransientNetworkChanged || hasStateErrors)) {
      jsErrors.length = 0;
      consoleErrors.length = 0;
      exceptions.length = 0;
      jsWarnings.length = 0;
      await delay(2000);
      continue;
    }
    break;
  }

  const payload = {
    dashboardUrl,
    result,
    exceptions: exceptions.map(item => item?.exceptionDetails?.text || 'exception'),
    consoleErrors,
    jsErrors,
    jsWarnings,
  };

  console.log(JSON.stringify(payload, null, 2));

  const failed =
    !result.hasOverviewKpis ||
    !result.hasDecisionStrip ||
    result.hasRefreshError ||
    result.hasNotDefined ||
    exceptions.length > 0 ||
    consoleErrors.length > 0 ||
    jsErrors.some(text => !/favicon\.ico|apple-touch-icon|manifest\.json/i.test(text));

  cleanup();
  if (failed) {
    process.exit(1);
  }
}

main().catch(error => {
  console.error(error?.stack || String(error));
  cleanup();
  process.exit(1);
});
