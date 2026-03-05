const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");

async function fetchOrders() {
  try {
    statusEl.textContent = "Actualizando…";
    const res = await fetch(`/admin/api/orders?limit=20&token=${encodeURIComponent(window.ADMIN_TOKEN || "")}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    grid.innerHTML = "";
    for (const o of data.orders) {
      const items = (o.items || []).map(it => `<li>${it.qty}x ${it.name}${it.config ? ` (${it.config})` : ""} — C$${it.price}</li>`).join("");
      const el = document.createElement("div");
      el.className = "card";
      el.innerHTML = `
        <div class="topline">
          <div class="ticket">${o.ticket}</div>
          <div class="badge">${o.delivery_mode || "—"} • ${o.payment_method || "—"}</div>
        </div>
        <div class="meta">
          ${o.customer_name || "—"} • ${o.wa_id || "—"}<br/>
          ${o.district_group || ""} ${o.address ? "• " + o.address : ""}
          <br/>🕒 ${o.created_at || "—"}
        </div>
        <ul>${items}</ul>
        <div class="total">Total: C$${o.total}</div>
      `;
      grid.appendChild(el);
    }

    statusEl.textContent = `OK • ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    statusEl.textContent = "Error de conexión";
    console.error(e);
  }
}

// primer load + refresco cada 3s
fetchOrders();
setInterval(fetchOrders, 3000);
