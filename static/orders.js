const deliveryGrid = document.getElementById("deliveryGrid");
const pickupGrid = document.getElementById("pickupGrid");

window.lastOrders = [];

const statusEl = document.getElementById("status");
const lastUpdateEl = document.getElementById("lastUpdate");
const deliveryCountEl = document.getElementById("deliveryCount");
const pickupCountEl = document.getElementById("pickupCount");
const filterStatusEl = document.getElementById("filterStatus");

let knownOrderIds = new Set();
let firstLoad = true;

const STATUS_PRIORITY = {
  pendiente: 1,
  preparando: 2,
  en_camino: 3,
  listo_retirar: 3,
  entregado: 4,
  cancelado: 5,
};

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

function getFilteredOrders(orders) {
  const selected = filterStatusEl.value;
  if (selected === "todos") return orders;
  return orders.filter((o) => o.status === selected);
}

function createActionButtons(order) {
  const isDelivery = (order.delivery_mode || "").toLowerCase() === "delivery";

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
  target.innerHTML = `
    <div class="empty">
      ${escapeHtml(text)}
    </div>
  `;
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

    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }

    await fetchOrders();
  } catch (e) {
    console.error("updateOrderStatus error:", e);
    alert("No se pudo cambiar el estado del pedido.");
    statusEl.textContent = "Error al cambiar estado";
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

async function fetchOrders() {
  try {
    statusEl.textContent = "Actualizando…";

    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/orders?limit=50&token=${encodeURIComponent(token)}`);

    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }

    const data = await res.json();
    const rawOrders = Array.isArray(data.orders) ? data.orders : [];

    window.lastOrders = rawOrders;

    detectNewOrders(rawOrders);

    const filtered = getFilteredOrders(rawOrders);
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

        if(order){
          printTicket(order);
        }

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

filterStatusEl.addEventListener("change", fetchOrders);

fetchOrders();
setInterval(fetchOrders, 3000);

function printTicket(order){

  const items = (order.items || [])
    .map(i => `${i.qty}x ${i.name} ${i.config ? "(" + i.config + ")" : ""}  C$${i.price}`)
    .join("<br>");

  const html = `
  <html>
  <head>
  <title>Ticket</title>
  <style>
  body{
    font-family: monospace;
    width:280px;
    padding:10px;
  }
  hr{
    border:none;
    border-top:1px dashed #000;
  }
  </style>
  </head>

  <body>

  <center>
  <b>DEACA</b><br>
  Fritanga Nica
  </center>

  <hr>

  Ticket: ${order.ticket}<br>
  Cliente: ${order.customer_name}<br>
  Tel: ${order.wa_id}<br>

  <hr>

  ${items}

  <hr>

  Total: C$${order.total}<br>
  Pago: ${order.payment_method}

  <hr>

  Gracias por su compra

  </body>
  </html>
  `;

  const win = window.open('', '', 'width=300,height=600');

  win.document.write(html);
  win.document.close();

  win.focus();
  win.print();
}
