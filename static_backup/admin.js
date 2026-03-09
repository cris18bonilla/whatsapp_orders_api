const adminStatus = document.getElementById("adminStatus");

const metricTotalOrders = document.getElementById("metricTotalOrders");
const metricRevenue = document.getElementById("metricRevenue");

const topProducts = document.getElementById("topProducts");
const lowProducts = document.getElementById("lowProducts");
const topDistricts = document.getElementById("topDistricts");
const lowDistricts = document.getElementById("lowDistricts");

const historyDate = document.getElementById("historyDate");
const loadHistoryBtn = document.getElementById("loadHistoryBtn");
const historyTotalOrders = document.getElementById("historyTotalOrders");
const historyRevenue = document.getElementById("historyRevenue");
const historyDeliveryCount = document.getElementById("historyDeliveryCount");
const historyPickupCount = document.getElementById("historyPickupCount");
const historyOrders = document.getElementById("historyOrders");

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function humanStatus(status) {
  switch (status) {
    case "pendiente": return "Pendiente";
    case "preparando": return "Preparando";
    case "en_camino": return "En camino";
    case "listo_retirar": return "Listo retirar";
    case "entregado": return "Entregado";
    case "cancelado": return "Cancelado";
    default: return status || "—";
  }
}

function formatDateTime(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function renderSimpleList(target, rows, type) {
  if (!rows || rows.length === 0) {
    target.innerHTML = `<div class="empty">Sin datos disponibles.</div>`;
    return;
  }

  target.innerHTML = rows.map(row => {
    const title = type === "district" ? row.district : row.name;
    const value = type === "district" ? `${row.orders} orden(es)` : `${row.qty} unidad(es)`;
    return `
      <div class="list-item">
        <div>
          <div class="list-title">${escapeHtml(title || "—")}</div>
          <div class="list-sub">Registrado en métricas</div>
        </div>
        <div class="tag">${escapeHtml(value)}</div>
      </div>
    `;
  }).join("");
}

function renderHistoryOrders(orders) {
  if (!orders || orders.length === 0) {
    historyOrders.innerHTML = `<div class="empty">No hay pedidos registrados para esta fecha.</div>`;
    return;
  }

  historyOrders.innerHTML = orders.map(order => {
    const items = (order.items || []).map(it => {
      const config = it.config ? ` (${escapeHtml(it.config)})` : "";
      return `<li>${escapeHtml(it.qty)}x ${escapeHtml(it.name)}${config} — C$${escapeHtml(it.price)}</li>`;
    }).join("");

    return `
      <div class="order-card">
        <div class="order-top">
          <div>
            <div class="ticket">${escapeHtml(order.ticket || "—")}</div>
            <div class="muted">${escapeHtml(formatDateTime(order.created_at))}</div>
          </div>
          <div class="status status-${escapeHtml(order.status || "pendiente")}">${escapeHtml(humanStatus(order.status))}</div>
        </div>

        <div class="muted">
          <strong>${escapeHtml(order.customer_name || "Cliente")}</strong><br>
          ${escapeHtml(order.wa_id || "—")}<br>
          ${escapeHtml(order.delivery_mode || "—")} • ${escapeHtml(order.payment_method || "—")}<br>
          ${escapeHtml(order.district_group || "")}${order.address ? " • " + escapeHtml(order.address) : ""}
        </div>

        <ul class="items">
          ${items || "<li>Sin items</li>"}
        </ul>
      </div>
    `;
  }).join("");
}

async function loadMetrics() {
  const token = window.ADMIN_TOKEN || "";
  const res = await fetch(`/admin/api/metrics?token=${encodeURIComponent(token)}`);
  if (!res.ok) throw new Error("No se pudo cargar métricas");

  const data = await res.json();

  metricTotalOrders.textContent = data.summary?.total_orders ?? 0;
  metricRevenue.textContent = `C$${data.summary?.total_revenue ?? 0}`;

  renderSimpleList(topProducts, data.top_products || [], "product");
  renderSimpleList(lowProducts, data.low_products || [], "product");
  renderSimpleList(topDistricts, data.top_districts || [], "district");
  renderSimpleList(lowDistricts, data.low_districts || [], "district");
}

async function loadHistory() {
  const token = window.ADMIN_TOKEN || "";
  const date = historyDate.value;
  if (!date) return;

  const res = await fetch(`/admin/api/history?date=${encodeURIComponent(date)}&token=${encodeURIComponent(token)}`);
  if (!res.ok) throw new Error("No se pudo cargar historial");

  const data = await res.json();

  historyTotalOrders.textContent = data.summary?.total_orders ?? 0;
  historyRevenue.textContent = `C$${data.summary?.total_revenue ?? 0}`;
  historyDeliveryCount.textContent = data.summary?.delivery_count ?? 0;
  historyPickupCount.textContent = data.summary?.pickup_count ?? 0;

  renderHistoryOrders(data.orders || []);
}

function todayInputValue() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function initAdmin() {
  try {
    adminStatus.textContent = "Cargando admin…";
    historyDate.value = todayInputValue();
    await loadMetrics();
    await loadHistory();
    adminStatus.textContent = "Admin conectado";
  } catch (e) {
    console.error(e);
    adminStatus.textContent = "Error admin";
    alert("No se pudo cargar el panel admin.");
  }
}

loadHistoryBtn.addEventListener("click", loadHistory);
initAdmin();
