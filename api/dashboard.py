import json
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from api.supabase_client import supabase
from api.config import CLIENT_ID, BUSINESS_NAME

router = APIRouter()


@router.get("/api/conversations")
async def get_conversations():
    query = supabase.table("conversations") \
        .select("customer_phone, customer_name, messages, last_message_at") \
        .order("last_message_at", desc=True)
    if CLIENT_ID:
        query = query.eq("client_id", CLIENT_ID)
    result = query.execute()
    rows = []
    for r in result.data:
        msgs = r.get("messages", [])
        if isinstance(msgs, str):
            msgs = json.loads(msgs)
        last_msg = ""
        if msgs:
            last = msgs[-1]
            parts = last.get("parts", [])
            last_msg = parts[0].get("text", "") if parts else ""
        rows.append({
            "phone": r["customer_phone"],
            "name": r["customer_name"],
            "last_message": last_msg[:80] + ("..." if len(last_msg) > 80 else ""),
            "last_message_at": r["last_message_at"],
            "message_count": len(msgs),
            "messages": msgs
        })
    return JSONResponse(content=rows)


@router.get("/api/appointments")
async def get_appointments():
    query = supabase.table("appointments") \
        .select("*") \
        .order("appointment_date", desc=True)
    if CLIENT_ID:
        query = query.eq("client_id", CLIENT_ID)
    result = query.execute()
    return JSONResponse(content=result.data)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html = DASHBOARD_HTML.replace("{{BUSINESS_NAME}}", BUSINESS_NAME)
    return HTMLResponse(content=html)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{BUSINESS_NAME}} — Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #1a1a1a; }

  /* Header */
  .header { background: #fff; border-bottom: 1px solid #e5e5e5; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10; }
  .header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }
  .header h1 span { color: #888; font-weight: 400; }
  .refresh-btn { font-size: 13px; color: #888; cursor: pointer; border: 1px solid #e5e5e5; background: #fafafa; padding: 6px 12px; border-radius: 6px; }
  .refresh-btn:hover { background: #f0f0f0; }
  .last-update { font-size: 12px; color: #bbb; }

  /* Tabs */
  .tabs { display: flex; gap: 0; border-bottom: 1px solid #e5e5e5; background: #fff; padding: 0 24px; }
  .tab { padding: 12px 16px; font-size: 14px; font-weight: 500; color: #888; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab.active { color: #1a1a1a; border-bottom-color: #1a1a1a; }
  .tab-badge { display: inline-block; background: #f0f0f0; color: #555; font-size: 11px; padding: 1px 6px; border-radius: 10px; margin-left: 6px; }
  .tab.active .tab-badge { background: #1a1a1a; color: #fff; }

  /* Content */
  .content { padding: 24px; max-width: 1100px; margin: 0 auto; }
  .panel { display: none; }
  .panel.active { display: block; }

  /* Stats row */
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .stat { background: #fff; border: 1px solid #e5e5e5; border-radius: 10px; padding: 16px; }
  .stat-label { font-size: 12px; color: #888; margin-bottom: 4px; }
  .stat-value { font-size: 26px; font-weight: 600; letter-spacing: -1px; }

  /* Table */
  .card { background: #fff; border: 1px solid #e5e5e5; border-radius: 10px; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th { text-align: left; padding: 12px 16px; font-size: 11px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #f0f0f0; background: #fafafa; }
  td { padding: 13px 16px; border-bottom: 1px solid #f5f5f5; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  tr.clickable { cursor: pointer; }
  tr.clickable:hover td { background: #fafafa; }

  /* Badges */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
  .badge-confirmed { background: #e8f5e9; color: #2e7d32; }
  .badge-cancelled { background: #fce4ec; color: #c62828; }
  .badge-pending { background: #fff8e1; color: #f57f17; }

  /* Conversation detail */
  .conv-name { font-weight: 500; }
  .conv-preview { color: #888; font-size: 13px; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px; }
  .conv-meta { font-size: 12px; color: #bbb; white-space: nowrap; }
  .msg-count { font-size: 12px; color: #888; }

  /* Modal */
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; align-items: center; justify-content: center; }
  .modal-overlay.open { display: flex; }
  .modal { background: #fff; border-radius: 12px; width: 90%; max-width: 560px; max-height: 80vh; display: flex; flex-direction: column; }
  .modal-header { padding: 18px 20px; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }
  .modal-header h2 { font-size: 15px; font-weight: 600; }
  .modal-close { font-size: 20px; cursor: pointer; color: #888; line-height: 1; }
  .modal-close:hover { color: #1a1a1a; }
  .modal-body { overflow-y: auto; padding: 16px 20px; flex: 1; display: flex; flex-direction: column; gap: 10px; }

  /* Chat bubbles */
  .bubble-row { display: flex; }
  .bubble-row.user { justify-content: flex-end; }
  .bubble-row.model { justify-content: flex-start; }
  .bubble { max-width: 78%; padding: 9px 13px; border-radius: 12px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
  .bubble-row.user .bubble { background: #1a1a1a; color: #fff; border-bottom-right-radius: 3px; }
  .bubble-row.model .bubble { background: #f0f0f0; color: #1a1a1a; border-bottom-left-radius: 3px; }

  /* Empty state */
  .empty { text-align: center; padding: 60px 20px; color: #bbb; }
  .empty-icon { font-size: 36px; margin-bottom: 12px; }
  .empty p { font-size: 14px; }

  /* Loading */
  .loading { text-align: center; padding: 40px; color: #bbb; font-size: 14px; }

  /* Price */
  .price { font-weight: 500; }

  @media (max-width: 600px) {
    .content { padding: 16px; }
    .stats { grid-template-columns: repeat(2, 1fr); }
    th:nth-child(n+4), td:nth-child(n+4) { display: none; }
  }
</style>
</head>
<body>

<div class="header">
  <h1>{{BUSINESS_NAME}} <span>/ Dashboard</span></h1>
  <div style="display:flex;align-items:center;gap:12px;">
    <span class="last-update" id="lastUpdate"></span>
    <button class="refresh-btn" onclick="loadAll()">↻ Actualizar</button>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('appointments')">
    Citas <span class="tab-badge" id="badge-appointments">0</span>
  </div>
  <div class="tab" onclick="switchTab('conversations')">
    Conversaciones <span class="tab-badge" id="badge-conversations">0</span>
  </div>
</div>

<div class="content">

  <!-- Appointments Panel -->
  <div class="panel active" id="panel-appointments">
    <div class="stats" id="appt-stats"></div>
    <div class="card" id="appt-table-wrap">
      <div class="loading">Cargando citas...</div>
    </div>
  </div>

  <!-- Conversations Panel -->
  <div class="panel" id="panel-conversations">
    <div class="stats" id="conv-stats"></div>
    <div class="card" id="conv-table-wrap">
      <div class="loading">Cargando conversaciones...</div>
    </div>
  </div>

</div>

<!-- Conversation Modal -->
<div class="modal-overlay" id="modal" onclick="closeModal(event)">
  <div class="modal">
    <div class="modal-header">
      <h2 id="modal-title">Conversación</h2>
      <span class="modal-close" onclick="closeModal()">✕</span>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
let appointments = [];
let conversations = [];

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['appointments','conversations'][i] === tab);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + tab).classList.add('active');
}

function formatDate(str) {
  if (!str) return '—';
  const d = new Date(str);
  return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatTime(str) {
  if (!str) return '—';
  return str.slice(0, 5);
}

function formatDateTime(str) {
  if (!str) return '—';
  const d = new Date(str);
  return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short' }) + ' ' +
    d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
}

function statusBadge(s) {
  const map = { confirmed: 'badge-confirmed', cancelled: 'badge-cancelled', pending: 'badge-pending' };
  const label = { confirmed: 'Confirmada', cancelled: 'Cancelada', pending: 'Pendiente' };
  return `<span class="badge ${map[s] || 'badge-pending'}">${label[s] || s}</span>`;
}

async function loadAppointments() {
  const res = await fetch('/api/appointments');
  appointments = await res.json();

  document.getElementById('badge-appointments').textContent = appointments.length;

  // Stats
  const confirmed = appointments.filter(a => a.status === 'confirmed').length;
  const total = appointments.reduce((s, a) => s + parseFloat(a.price || 0), 0);
  const today = new Date().toISOString().slice(0,10);
  const todayCount = appointments.filter(a => a.appointment_date === today).length;

  document.getElementById('appt-stats').innerHTML = `
    <div class="stat"><div class="stat-label">Total citas</div><div class="stat-value">${appointments.length}</div></div>
    <div class="stat"><div class="stat-label">Confirmadas</div><div class="stat-value">${confirmed}</div></div>
    <div class="stat"><div class="stat-label">Hoy</div><div class="stat-value">${todayCount}</div></div>
    <div class="stat"><div class="stat-label">Ingresos</div><div class="stat-value">$${total.toLocaleString('es-MX')}</div></div>
  `;

  if (appointments.length === 0) {
    document.getElementById('appt-table-wrap').innerHTML = `
      <div class="empty"><div class="empty-icon">📅</div><p>Aún no hay citas registradas</p></div>`;
    return;
  }

  const rows = appointments.map(a => `
    <tr>
      <td><strong>${a.customer_name}</strong><br><span style="font-size:12px;color:#888">${a.customer_phone}</span></td>
      <td>${a.service}</td>
      <td>${a.notes || '—'}</td>
      <td>${formatDate(a.appointment_date)}</td>
      <td>${formatTime(a.start_time)} – ${formatTime(a.end_time)}</td>
      <td class="price">$${parseFloat(a.price).toLocaleString('es-MX')}</td>
      <td>${statusBadge(a.status)}</td>
    </tr>
  `).join('');

  document.getElementById('appt-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Cliente</th><th>Servicio</th><th>Barbero</th><th>Fecha</th><th>Hora</th><th>Precio</th><th>Estado</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function loadConversations() {
  const res = await fetch('/api/conversations');
  conversations = await res.json();

  document.getElementById('badge-conversations').textContent = conversations.length;

  const totalMsgs = conversations.reduce((s, c) => s + c.message_count, 0);

  document.getElementById('conv-stats').innerHTML = `
    <div class="stat"><div class="stat-label">Clientes</div><div class="stat-value">${conversations.length}</div></div>
    <div class="stat"><div class="stat-label">Total mensajes</div><div class="stat-value">${totalMsgs}</div></div>
  `;

  if (conversations.length === 0) {
    document.getElementById('conv-table-wrap').innerHTML = `
      <div class="empty"><div class="empty-icon">💬</div><p>Aún no hay conversaciones</p></div>`;
    return;
  }

  const rows = conversations.map((c, i) => `
    <tr class="clickable" onclick="openConversation(${i})">
      <td>
        <div class="conv-name">${c.name}</div>
        <div class="conv-preview">${c.last_message || '—'}</div>
      </td>
      <td style="white-space:nowrap">${c.phone}</td>
      <td class="msg-count">${c.message_count}</td>
      <td class="conv-meta">${formatDateTime(c.last_message_at)}</td>
    </tr>
  `).join('');

  document.getElementById('conv-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Cliente</th><th>Teléfono</th><th>Msgs</th><th>Último mensaje</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function openConversation(i) {
  const c = conversations[i];
  document.getElementById('modal-title').textContent = `${c.name} · ${c.phone}`;

  const bubbles = c.messages.map(m => {
    const role = m.role;
    const parts = m.parts || [];
    const text = parts[0]?.text || '';
    if (!text) return '';
    return `<div class="bubble-row ${role}"><div class="bubble">${text}</div></div>`;
  }).join('');

  document.getElementById('modal-body').innerHTML = bubbles || '<p style="color:#bbb;text-align:center">Sin mensajes</p>';
  document.getElementById('modal').classList.add('open');

  // Scroll to bottom
  setTimeout(() => {
    const body = document.getElementById('modal-body');
    body.scrollTop = body.scrollHeight;
  }, 50);
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal')) {
    document.getElementById('modal').classList.remove('open');
  }
}

async function loadAll() {
  await Promise.all([loadAppointments(), loadConversations()]);
  document.getElementById('lastUpdate').textContent =
    'Actualizado: ' + new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
}

// Auto-refresh every 60 seconds
loadAll();
setInterval(loadAll, 60000);
</script>
</body>
</html>
"""
