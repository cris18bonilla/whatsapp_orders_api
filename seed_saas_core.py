from db import SessionLocal
from models_saas import MenuMainItem, Permission

db = SessionLocal()

# =========================
# MAIN ITEMS
# =========================
main_items = [
    {"code": "menu", "default_name": "Menú", "sort_order": 1},
    {"code": "location", "default_name": "Ubicación", "sort_order": 2},
    {"code": "advisor", "default_name": "Asesor", "sort_order": 3},
    {"code": "clear_order", "default_name": "Borrar orden", "sort_order": 4},
]

for item in main_items:
    exists = db.query(MenuMainItem).filter(MenuMainItem.code == item["code"]).first()
    if not exists:
        db.add(MenuMainItem(**item))

# =========================
# PERMISSIONS
# =========================
permissions = [
    ("view_admin_dashboard", "Ver dashboard admin", "admin_core"),
    ("manage_users", "Gestionar usuarios", "admin_core"),
    ("manage_roles", "Gestionar roles", "admin_core"),
    ("view_logs", "Ver bitácora", "admin_core"),
    ("export_reports", "Exportar reportes", "admin_core"),

    ("use_delivery_pos", "Usar POS Delivery", "delivery_pos"),
    ("assign_driver", "Asignar driver", "delivery_pos"),
    ("update_delivery_status", "Cambiar estado delivery", "delivery_pos"),

    ("use_local_pos", "Usar POS Local", "local_pos"),
    ("create_local_order", "Crear comanda local", "local_pos"),
    ("close_local_order", "Cerrar orden local", "local_pos"),

    ("view_hr", "Ver RRHH", "hr_module"),
    ("mark_attendance", "Marcar asistencia", "hr_module"),
    ("manage_employees", "Gestionar empleados", "hr_module"),

    ("view_inventory", "Ver inventario", "inventory_module"),
    ("adjust_inventory", "Ajustar inventario", "inventory_module"),
    ("register_purchase", "Registrar compra", "inventory_module"),

    ("open_cash", "Abrir caja", "cash_module"),
    ("close_cash", "Cerrar caja", "cash_module"),
    ("view_cash_reports", "Ver reportes de caja", "cash_module"),

    ("view_analytics", "Ver analíticas", "analytics_module"),
]

for code, name, module_code in permissions:
    exists = db.query(Permission).filter(Permission.code == code).first()
    if not exists:
        db.add(Permission(code=code, name=name, module_code=module_code))

db.commit()
db.close()

print("Seed SaaS core completado.")
