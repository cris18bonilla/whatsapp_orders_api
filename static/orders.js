const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function renderEmpty() {
  grid.innerHTML = `
    <div class="empty">
      <div style="font-size:18px;font-weight:700;margin-bottom:8px;">No hay pedidos todavía</div>
      <div>Cuando entre un pedido confirmado, aparecerá aquí automáticamente.</div>
    </div>
  `;
}

async function fetchOrders() {
  try {
    statusEl.textContent = "Actualizando…";

    const token = window.ADMIN_TOKEN || "";
    const res = await fetch(`/admin/api/orders?limit=20&token=${encodeURIComponent(token)}`);

    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }

    const data = await res.json();
    const orders = Array.isArray(data.orders) ? data.orders : [];

    grid.innerHTML = "";

    if (orders.length === 0) {
      renderEmpty();
      statusEl.textContent = `Sin pedidos • ${new Date().toLocaleTimeString()}`;
      return;
    }

    for (const o of orders) {
      const items = (o.items || [])
        .map(
          (it) =>
            `<li>${it.qty}x ${it.name}${it.config ? ` (${it.config})` : ""} — C$${it.price}</li>`
        )
        .join("");

      const el = document.createElement("div");
      el.className = "card";
      el.innerHTML = `
        <div class="topline">
          <div class="ticket">${o.ticket || "—"}</div>
          <div class="badge">${o.delivery_mode || "—"} • ${o.payment_method || "—"}</div>
        </div>
        <div class="meta">
          ${o.customer_name || "—"} • ${o.wa_id || "—"}<br/>
          ${o.district_group || ""}${o.address ? " • " + o.address : ""}
          <br/>🕒 ${formatDate(o.created_at)}
        </div>
        <ul>${items || "<li>Sin items</li>"}</ul>
        <div class="total">Total: C$${o.total ?? 0}</div>
      `;
      grid.appendChild(el);
    }

    statusEl.textContent = `OK • ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    statusEl.textContent = "Error de conexión";
    console.error("fetchOrders error:", e);
  }
}

fetchOrders();
setInterval(fetchOrders, 3000);
