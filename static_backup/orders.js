const deliveryGrid = document.getElementById("deliveryGrid");
const pickupGrid = document.getElementById("pickupGrid");

window.lastOrders = [];

const statusEl = document.getElementById("status");
const lastUpdateEl = document.getElementById("lastUpdate");
const deliveryCountEl = document.getElementById("deliveryCount");
const pickupCountEl = document.getElementById("pickupCount");
const filterStatusEl = document.getElementById("filterStatus");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const adminBtn = document.getElementById("adminBtn");

let knownOrderIds = new Set();
let firstLoad = true;
let adminUnlocked = false;

const STATUS_PRIORITY = {
  pendiente: 1,
  preparando: 2,
  en_camino: 3,
  listo_retirar: 3,
  entregado: 4,
  cancelado: 5,
};

const ACTIVE_STATUSES = ["pendiente", "preparando", "en_camino", "listo_retirar"];

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function humanStatus(status) {
  switch (status) {
    case "pendiente":
      return "Pendiente";
    case "preparando":
      return "Preparando";
    case "en_camino":
      return "En camino";
    case "listo_retirar":
      return "Listo retirar";
    case "entregado":
      return "Entregado";
    case "cancelado":
      return "Cancelado";
    default:
      return status || "—";
  }
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function playNewOrderSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.45);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.45);
  } catch (e) {
    console.warn("No se pudo reproducir sonido:", e);
  }
}

function sortOrders(orders) {
  return [...orders].sort((a, b) => {
    const pa = STATUS_PRIORITY[a.status] || 999;
    const pb = STATUS_PRIORITY[b.status] || 999;

    if (pa !== pb) return pa - pb;

    const ida = Number(a.id || 0);
    const idb = Number(b.id || 0);
    return ida - idb;
  });
}

function getVisibleKdsOrders(orders) {
  return orders.filter((o) => !o.hidden_from_kds);
}

function getFilteredOrders(orders) {
  const selected = filterStatusEl.value;
  if (selected === "todos") return orders;
  if (selected === "activos") {
    return orders.filter((o) => ACTIVE_STATUSES.includes(o.status));
  }
  return orders.filter((o) => o.status === selected);
}

function createActionButtons(order) {
  const isDelivery = (order.delivery_mode || "").toLowerCase() === "delivery";

  let extraAction = "";
  if (order.status === "entregado") {
    extraAction = `<button class="btn btn-outline hide-btn" data-order-id="${order.id}">Retirar de pantalla</button>`;
  } else if (order.status === "cancelado") {
    extraAction = `<button class="btn btn-outline delete-cancelled-btn" data-order-id="${order.id}">Eliminar cancelado</button>`;
  }

  return `
    <div class="actions">
      <button class="btn btn-pending" data-order-id="${order.id}" data-status="pendiente">Pendiente</button>
      <button class="btn btn-preparing" data-order-id="${order.id}" data-status="preparando">Preparando</button>
      ${
        isDelivery
          ? `<button class="btn btn-onway" data-order-id="${order.id}" data-status="en_camino">En camino</button>`
          : `<button class="btn btn-pickup" data-order-id="${order.id}" data-status="listo_retirar">Listo retirar</button>`
      }
      <button class="btn btn-delivered" data-order-id="${order.id}" data-status="entregado">Entregado</button>
      <button class="btn btn-cancelled" data-order-id="${order.id}" data-status="cancelado">Cancelado</button>
      <button class="btn btn-outline print-btn" data-ticket="${order.ticket}">🖨 Imprimir</button>
      ${extraAction}
    </div>
  `;
}

function renderCard(order) {
  const itemsHtml = (order.items || [])
    .map((it) => {
      const config = it.config ? ` (${escapeHtml(it.config)})` : "";
      return `<li>${escapeHtml(it.qty)}x ${escapeHtml(it.name)}${config} — C$${escapeHtml(it.price)}</li>`;
    })
    .join("");

  return `
    <article class="card">
      <div class="card-top">
        <div class="ticket">${escapeHtml(order.ticket || "—")}</div>
        <div class="status-pill status-${escapeHtml(order.status || "pendiente")}">${escapeHtml(humanStatus(order.status))}</div>
      </div>

      <div class="card-meta">
        <div class="line-strong">${escapeHtml(order.customer_name || "Cliente sin nombre")}</div>
        ${escapeHtml(order.wa_id || "—")}<br/>
        ${escapeHtml(order.delivery_mode || "—")} • ${escapeHtml(order.payment_method || "—")}<br/>
        ${escapeHtml(order.district_group || "")}${order.address ? " • " + escapeHtml(order.address) : ""}<br/>
        🕒 ${escapeHtml(formatDate(order.created_at))}
      </div>

      <ul class="items">
        ${itemsHtml || "<li>Sin items</li>"}
      </ul>

      <div class="card-footer">
        <div class="total">Total: C$${escapeHtml(order.total ?? 0)}</div>
        ${createActionButtons(order)}
      </div>
    </article>
  `;
}

function renderEmpty(target, text) {
  target.innerHTML = `<div class="empty">${escapeHtml(text)}</div>`;
}

function updateCounts(deliveryOrders, pickupOrders) {
  deliveryCountEl.textContent = `${deliveryOrders.length} pedido(s)`;
  pickupCountEl.textContent = `${pickupOrders.length} pedido(s)`;
}

async function updateOrderStatus(orderId, status) {
  try {
    statusEl.textContent = "Actualizando estado…";

    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/orders/${orderId}/status?token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status }),
    });

    if (!res.ok) throw new Error("HTTP " + res.status);

    await fetchOrders();
  } catch (e) {
    console.error("updateOrderStatus error:", e);
    alert("No se pudo cambiar el estado del pedido.");
    statusEl.textContent = "Error al cambiar estado";
  }
}

async function hideDeliveredOrder(orderId) {
  const pin = window.prompt("Ingresa el PIN admin para retirar este pedido de pantalla:");
  if (!pin) return;

  try {
    statusEl.textContent = "Retirando pedido…";

    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/orders/${orderId}/hide?token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || ("HTTP " + res.status));
    }

    await fetchOrders();
  } catch (e) {
    console.error("hideDeliveredOrder error:", e);
    alert(`No se pudo retirar el pedido: ${e.message}`);
    statusEl.textContent = "Error al retirar";
  }
}

async function deleteCancelledOrder(orderId) {
  const pin = window.prompt("Ingresa el PIN admin para eliminar este pedido cancelado:");
  if (!pin) return;

  const ok = window.confirm("Esta acción eliminará el pedido cancelado de la base de datos. ¿Deseas continuar?");
  if (!ok) return;

  try {
    statusEl.textContent = "Eliminando cancelado…";

    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/orders/${orderId}/delete-cancelled?token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || ("HTTP " + res.status));
    }

    await fetchOrders();
  } catch (e) {
    console.error("deleteCancelledOrder error:", e);
    alert(`No se pudo eliminar el pedido cancelado: ${e.message}`);
    statusEl.textContent = "Error al eliminar";
  }
}

function bindActionButtons() {
  document.querySelectorAll("[data-order-id][data-status]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const orderId = btn.getAttribute("data-order-id");
      const status = btn.getAttribute("data-status");
      await updateOrderStatus(orderId, status);
    });
  });

  document.querySelectorAll(".hide-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const orderId = btn.getAttribute("data-order-id");
      await hideDeliveredOrder(orderId);
    });
  });

  document.querySelectorAll(".delete-cancelled-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const orderId = btn.getAttribute("data-order-id");
      await deleteCancelledOrder(orderId);
    });
  });
}

function detectNewOrders(orders) {
  const currentIds = new Set(orders.map((o) => o.id));
  const hasNewOrder = [...currentIds].some((id) => !knownOrderIds.has(id));

  if (!firstLoad && hasNewOrder) {
    playNewOrderSound();
  }

  knownOrderIds = currentIds;
  firstLoad = false;
}

function printTicket(order) {
  const logoUrl = window.LOGO_URL || "/static/logo.png";

  const items = (order.items || [])
    .map(i => `${i.qty}x ${i.name}${i.config ? " (" + i.config + ")" : ""} .... C$${i.price}`)
    .join("<br>");

  const ticketBlock = `
    <div class="ticket-copy">
      <div class="center">
        <img src="${logoUrl}" class="logo" alt="DEACA POS"><br>
        <strong>DEACA POS</strong><br>
        Fritanga Nica
      </div>

      <div class="line"></div>

      Ticket: ${order.ticket}<br>
      Cliente: ${order.customer_name || "Cliente"}<br>
      Tel: ${order.wa_id || "-"}<br>
      Entrega: ${order.delivery_mode || "-"}<br>
      Pago: ${order.payment_method || "-"}<br>
      Estado: ${humanStatus(order.status)}<br>
      ${order.district_group ? `Distrito: ${order.district_group}<br>` : ""}
      ${order.address ? `Dirección: ${order.address}<br>` : ""}

      <div class="line"></div>

      ${items || "Sin items"}

      <div class="line"></div>

      Subtotal: C$${order.subtotal ?? 0}<br>
      Envío: C$${order.delivery_fee ?? 0}<br>
      <strong>Total: C$${order.total ?? 0}</strong><br>

      <div class="line"></div>

      Gracias por su compra
    </div>
  `;

  const html = `
  <html>
  <head>
    <title>Ticket ${order.ticket}</title>
    <style>
      @page { size: 80mm auto; margin: 2mm; }
      body {
        font-family: monospace;
        width: 76mm;
        margin: 0 auto;
        padding: 0;
        font-size: 11px;
        line-height: 1.35;
      }
      .center { text-align: center; }
      .logo { width: 26mm; height: auto; object-fit: contain; }
      .line { border-top: 1px dashed #000; margin: 6px 0; }
      .cut { text-align: center; margin: 8px 0; font-size: 10px; }
      .ticket-copy { padding-bottom: 8px; }
    </style>
  </head>
  <body>
    ${ticketBlock}
    <div class="cut">---------------- COPIA CLIENTE ----------------</div>
    ${ticketBlock}
    <script>
      window.onload = function() {
        window.focus();
        window.print();
      }
    <\/script>
  </body>
  </html>
  `;

  const win = window.open("", "", "width=420,height=700");
  win.document.write(html);
  win.document.close();
}

function promptAdminPin() {
  const pin = window.prompt("Ingresa el PIN admin:");
  if (!pin) return null;
  return pin;
}

async function validateAdminPin(pin) {
  try {
    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/metrics?token=${encodeURIComponent(token)}`, {
      method: "GET",
      headers: {
        "X-Admin-Pin": pin,
      },
    });

    return res.ok;
  } catch {
    return false;
  }
}

async function handleAdminAccess(event) {
  event.preventDefault();

  if (adminUnlocked) {
    const token = encodeURIComponent(window.ADMIN_TOKEN || "");
    window.location.href = `/admin?token=${token}`;
    return;
  }

  const pin = promptAdminPin();
  if (!pin) return;

  try {
    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/pin-check?token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });

    if (!res.ok) {
      alert("PIN incorrecto.");
      return;
    }

    adminUnlocked = true;
    const encodedToken = encodeURIComponent(window.ADMIN_TOKEN || "");
    window.location.href = `/admin?token=${encodedToken}`;
  } catch (e) {
    console.error("handleAdminAccess error:", e);
    alert("No se pudo validar el PIN.");
  }
}

async function fetchOrders() {
  try {
    statusEl.textContent = "Actualizando…";

    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/orders?limit=100&token=${encodeURIComponent(token)}`);

    if (!res.ok) throw new Error("HTTP " + res.status);

    const data = await res.json();
    const rawOrders = Array.isArray(data.orders) ? data.orders : [];

    window.lastOrders = rawOrders;

    const visibleOrders = getVisibleKdsOrders(rawOrders);
    detectNewOrders(visibleOrders);

    const filtered = getFilteredOrders(visibleOrders);
    const sorted = sortOrders(filtered);

    const deliveryOrders = sorted.filter(
      (o) => (o.delivery_mode || "").toLowerCase() === "delivery"
    );
    const pickupOrders = sorted.filter(
      (o) => (o.delivery_mode || "").toLowerCase() !== "delivery"
    );

    deliveryGrid.innerHTML = "";
    pickupGrid.innerHTML = "";

    if (deliveryOrders.length === 0) {
      renderEmpty(deliveryGrid, "No hay pedidos delivery en esta vista.");
    } else {
      deliveryGrid.innerHTML = deliveryOrders.map(renderCard).join("");
    }

    if (pickupOrders.length === 0) {
      renderEmpty(pickupGrid, "No hay pedidos de retiro en esta vista.");
    } else {
      pickupGrid.innerHTML = pickupOrders.map(renderCard).join("");
    }

    updateCounts(deliveryOrders, pickupOrders);
    bindActionButtons();

    document.querySelectorAll(".print-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const ticket = btn.dataset.ticket;
        const order = window.lastOrders.find(o => o.ticket === ticket);
        if (order) printTicket(order);
      });
    });

    const now = new Date().toLocaleTimeString();
    statusEl.textContent = "Conectado";
    lastUpdateEl.textContent = `Actualizado: ${now}`;
  } catch (e) {
    console.error("fetchOrders error:", e);
    statusEl.textContent = "Error de conexión";
    lastUpdateEl.textContent = "Sin actualizar";
  }
}

if (filterStatusEl) {
  filterStatusEl.addEventListener("change", fetchOrders);
}

if (fullscreenBtn) {
  fullscreenBtn.addEventListener("click", async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch (e) {
      console.warn("No se pudo activar pantalla completa", e);
    }
  });
}

if (adminBtn) {
  adminBtn.addEventListener("click", handleAdminAccess);
}

fetchOrders();
setInterval(fetchOrders, 3000);
