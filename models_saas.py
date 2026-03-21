from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Float,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from db import Base


# =========================================================
# CORE
# =========================================================

class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(120), nullable=False)
    slug = Column(String(120), unique=True, index=True, nullable=False)

    brand_name = Column(String(120), nullable=True)
    tagline = Column(String(180), nullable=True)

    logo_url = Column(Text, nullable=True)

    ruc = Column(String(80), nullable=True)
    address = Column(Text, nullable=True)
    schedule = Column(Text, nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    whatsapp_phone_number_id = Column(String(80), unique=True, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    modules = relationship("RestaurantModule", back_populates="restaurant", cascade="all, delete-orphan")
    settings = relationship("RestaurantSetting", back_populates="restaurant", cascade="all, delete-orphan")
    users = relationship("RestaurantUser", back_populates="restaurant", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="restaurant", cascade="all, delete-orphan")
    logs = relationship("ActivityLog", back_populates="restaurant", cascade="all, delete-orphan")

    main_item_settings = relationship("RestaurantMainItemSetting", back_populates="restaurant", cascade="all, delete-orphan")
    subcategories = relationship("MenuSubcategory", back_populates="restaurant", cascade="all, delete-orphan")
    products = relationship("MenuProduct", back_populates="restaurant", cascade="all, delete-orphan")

    drivers = relationship("Driver", back_populates="restaurant", cascade="all, delete-orphan")
    delivery_orders = relationship("DeliveryOrder", back_populates="restaurant", cascade="all, delete-orphan")

    tables = relationship("DiningTable", back_populates="restaurant", cascade="all, delete-orphan")
    local_orders = relationship("LocalOrder", back_populates="restaurant", cascade="all, delete-orphan")

    employee_profiles = relationship("EmployeeProfile", back_populates="restaurant", cascade="all, delete-orphan")
    attendance_logs = relationship("AttendanceLog", back_populates="restaurant", cascade="all, delete-orphan")

    suppliers = relationship("Supplier", back_populates="restaurant", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="restaurant", cascade="all, delete-orphan")
    inventory_purchases = relationship("InventoryPurchaseHeader", back_populates="restaurant", cascade="all, delete-orphan")
    inventory_movements = relationship("InventoryMovement", back_populates="restaurant", cascade="all, delete-orphan")

    cash_sessions = relationship("CashSession", back_populates="restaurant", cascade="all, delete-orphan")
    cash_movements = relationship("CashMovement", back_populates="restaurant", cascade="all, delete-orphan")
    cash_closing_templates = relationship("CashClosingTemplate", back_populates="restaurant", cascade="all, delete-orphan")
    cash_closings = relationship("CashClosing", back_populates="restaurant", cascade="all, delete-orphan")

    daily_metrics = relationship("DailyMetric", back_populates="restaurant", cascade="all, delete-orphan")
    product_sales_metrics = relationship("ProductSalesMetric", back_populates="restaurant", cascade="all, delete-orphan")
    user_sales_metrics = relationship("UserSalesMetric", back_populates="restaurant", cascade="all, delete-orphan")
    driver_metrics = relationship("DriverMetric", back_populates="restaurant", cascade="all, delete-orphan")

    exports = relationship("ExportJob", back_populates="restaurant", cascade="all, delete-orphan")


class RestaurantModule(Base):
    __tablename__ = "restaurant_modules"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "module_code", name="uq_restaurant_module"),
    )

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    module_code = Column(String(50), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    activated_at = Column(DateTime(timezone=True), nullable=True)

    restaurant = relationship("Restaurant", back_populates="modules")


class RestaurantSetting(Base):
    __tablename__ = "restaurant_settings"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "setting_key", name="uq_restaurant_setting"),
    )

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    setting_key = Column(String(100), nullable=False, index=True)
    setting_value = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="settings")


# =========================================================
# USERS / ROLES / PERMISSIONS
# =========================================================

class RestaurantUser(Base):
    __tablename__ = "restaurant_users"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(120), nullable=False)
    pin_code = Column(String(50), nullable=False)  # luego puedes migrarlo a pin hash

    role_code = Column(String(50), nullable=False, default="staff", server_default="staff")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    restaurant = relationship("Restaurant", back_populates="users")

    permissions = relationship("UserPermission", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    logs = relationship("ActivityLog", back_populates="user")
    employee_profile = relationship("EmployeeProfile", back_populates="user", uselist=False)


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False)
    module_code = Column(String(50), nullable=False)

    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    user_permissions = relationship("UserPermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_code", "permission_id", name="uq_role_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)

    role_code = Column(String(50), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)

    permission = relationship("Permission", back_populates="role_permissions")


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)

    is_allowed = Column(Boolean, nullable=False, default=True, server_default="1")

    user = relationship("RestaurantUser", back_populates="permissions")
    permission = relationship("Permission", back_populates="user_permissions")


# =========================================================
# LOGS / SESSIONS
# =========================================================

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="CASCADE"), nullable=False, index=True)

    module_code = Column(String(50), nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    ip_address = Column(String(120), nullable=True)
    user_agent = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="sessions")
    user = relationship("RestaurantUser", back_populates="sessions")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    module_code = Column(String(50), nullable=False, index=True)
    action_code = Column(String(100), nullable=False, index=True)
    action_label = Column(String(200), nullable=False)

    target_type = Column(String(100), nullable=True)
    target_id = Column(Integer, nullable=True)

    metadata_json = Column(Text, nullable=True)

    ip_address = Column(String(120), nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="logs")
    user = relationship("RestaurantUser", back_populates="logs")


# =========================================================
# MENU / CATALOG
# =========================================================

class MenuMainItem(Base):
    __tablename__ = "menu_main_items"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(50), nullable=False, unique=True, index=True)
    default_name = Column(String(100), nullable=False)

    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_system_fixed = Column(Boolean, nullable=False, default=True, server_default="1")

    restaurant_settings = relationship("RestaurantMainItemSetting", back_populates="main_item", cascade="all, delete-orphan")


class RestaurantMainItemSetting(Base):
    __tablename__ = "restaurant_main_item_settings"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "main_item_id", name="uq_restaurant_main_item"),
    )

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    main_item_id = Column(Integer, ForeignKey("menu_main_items.id", ondelete="CASCADE"), nullable=False, index=True)

    custom_name = Column(String(100), nullable=True)
    is_visible = Column(Boolean, nullable=False, default=True, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    restaurant = relationship("Restaurant", back_populates="main_item_settings")
    main_item = relationship("MenuMainItem", back_populates="restaurant_settings")


class MenuSubcategory(Base):
    __tablename__ = "menu_subcategories"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)

    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    show_in_delivery = Column(Boolean, nullable=False, default=True, server_default="1")
    show_in_local = Column(Boolean, nullable=False, default=True, server_default="1")

    restaurant = relationship("Restaurant", back_populates="subcategories")
    products = relationship("MenuProduct", back_populates="subcategory", cascade="all, delete-orphan")


class MenuProduct(Base):
    __tablename__ = "menu_products"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    subcategory_id = Column(Integer, ForeignKey("menu_subcategories.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(180), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False, default=0, server_default="0")

    image_url = Column(Text, nullable=True)
    sku = Column(String(80), nullable=True, index=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    show_in_delivery = Column(Boolean, nullable=False, default=True, server_default="1")
    show_in_local = Column(Boolean, nullable=False, default=True, server_default="1")

    requires_quantity_prompt = Column(Boolean, nullable=False, default=True, server_default="1")

    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="products")
    subcategory = relationship("MenuSubcategory", back_populates="products")

    option_groups = relationship("ProductOptionGroup", back_populates="product", cascade="all, delete-orphan")
    recipes = relationship("ProductRecipe", back_populates="product", cascade="all, delete-orphan")


class ProductOptionGroup(Base):
    __tablename__ = "product_option_groups"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("menu_products.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(120), nullable=False)

    min_select = Column(Integer, nullable=False, default=0, server_default="0")
    max_select = Column(Integer, nullable=False, default=1, server_default="1")

    is_required = Column(Boolean, nullable=False, default=False, server_default="0")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    product = relationship("MenuProduct", back_populates="option_groups")
    values = relationship("ProductOptionValue", back_populates="group", cascade="all, delete-orphan")


class ProductOptionValue(Base):
    __tablename__ = "product_option_values"

    id = Column(Integer, primary_key=True, index=True)

    option_group_id = Column(Integer, ForeignKey("product_option_groups.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(120), nullable=False)
    extra_price = Column(Integer, nullable=False, default=0, server_default="0")

    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    group = relationship("ProductOptionGroup", back_populates="values")


# =========================================================
# DELIVERY POS
# =========================================================

class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(120), nullable=False)
    phone = Column(String(30), nullable=True)
    vehicle_type = Column(String(80), nullable=True)
    plate = Column(String(30), nullable=True)

    total_distance_km = Column(Float, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="drivers")
    orders = relationship("DeliveryOrder", back_populates="driver")


class DeliveryOrder(Base):
    __tablename__ = "delivery_orders"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True)

    ticket = Column(String(50), nullable=False, unique=True, index=True)

    wa_id = Column(String(32), nullable=True, index=True)
    customer_name = Column(String(120), nullable=True)

    order_channel = Column(String(20), nullable=False, default="delivery", server_default="delivery")  # delivery / pickup
    status = Column(String(30), nullable=False, default="pendiente", server_default="pendiente")

    payment_method = Column(String(30), nullable=True)

    cash_currency = Column(String(10), nullable=True)  # NIO / USD
    cash_received = Column(Float, nullable=True)
    cash_received_nio = Column(Float, nullable=True)
    exchange_rate_used = Column(Float, nullable=True)
    change_due_nio = Column(Float, nullable=True)

    subtotal = Column(Integer, nullable=False, default=0, server_default="0")
    delivery_fee = Column(Integer, nullable=False, default=0, server_default="0")
    tax_amount = Column(Integer, nullable=False, default=0, server_default="0")
    total = Column(Integer, nullable=False, default=0, server_default="0")

    address = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    preparing_at = Column(DateTime(timezone=True), nullable=True)
    out_for_delivery_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    hidden_from_kds = Column(Boolean, nullable=False, default=False, server_default="0")

    restaurant = relationship("Restaurant", back_populates="delivery_orders")
    driver = relationship("Driver", back_populates="orders")

    items = relationship("DeliveryOrderItem", back_populates="order", cascade="all, delete-orphan")


class DeliveryOrderItem(Base):
    __tablename__ = "delivery_order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(Integer, ForeignKey("delivery_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("menu_products.id", ondelete="SET NULL"), nullable=True, index=True)

    name_snapshot = Column(String(180), nullable=False)
    description_snapshot = Column(Text, nullable=True)

    unit_price = Column(Integer, nullable=False, default=0, server_default="0")
    qty = Column(Integer, nullable=False, default=1, server_default="1")
    line_total = Column(Integer, nullable=False, default=0, server_default="0")

    order = relationship("DeliveryOrder", back_populates="items")
    options = relationship("DeliveryOrderItemOption", back_populates="order_item", cascade="all, delete-orphan")


class DeliveryOrderItemOption(Base):
    __tablename__ = "delivery_order_item_options"

    id = Column(Integer, primary_key=True, index=True)

    order_item_id = Column(Integer, ForeignKey("delivery_order_items.id", ondelete="CASCADE"), nullable=False, index=True)

    option_group_name = Column(String(120), nullable=False)
    option_value_name = Column(String(120), nullable=False)
    extra_price = Column(Integer, nullable=False, default=0, server_default="0")

    order_item = relationship("DeliveryOrderItem", back_populates="options")


# =========================================================
# LOCAL POS
# =========================================================

class DiningTable(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(50), nullable=False)
    capacity = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    restaurant = relationship("Restaurant", back_populates="tables")
    orders = relationship("LocalOrder", back_populates="table")


class LocalOrder(Base):
    __tablename__ = "local_orders"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    table_id = Column(Integer, ForeignKey("tables.id", ondelete="SET NULL"), nullable=True, index=True)
    waiter_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    ticket = Column(String(50), nullable=False, unique=True, index=True)

    status = Column(String(30), nullable=False, default="abierta", server_default="abierta")
    payment_method = Column(String(30), nullable=True)

    cash_currency = Column(String(10), nullable=True)
    cash_received = Column(Float, nullable=True)
    cash_received_nio = Column(Float, nullable=True)
    exchange_rate_used = Column(Float, nullable=True)
    change_due_nio = Column(Float, nullable=True)

    subtotal = Column(Integer, nullable=False, default=0, server_default="0")
    tax_amount = Column(Integer, nullable=False, default=0, server_default="0")
    total = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_to_kitchen_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    hidden_from_local_kds = Column(Boolean, nullable=False, default=False, server_default="0")

    restaurant = relationship("Restaurant", back_populates="local_orders")
    table = relationship("DiningTable", back_populates="orders")

    items = relationship("LocalOrderItem", back_populates="order", cascade="all, delete-orphan")


class LocalOrderItem(Base):
    __tablename__ = "local_order_items"

    id = Column(Integer, primary_key=True, index=True)

    local_order_id = Column(Integer, ForeignKey("local_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("menu_products.id", ondelete="SET NULL"), nullable=True, index=True)

    name_snapshot = Column(String(180), nullable=False)
    unit_price = Column(Integer, nullable=False, default=0, server_default="0")
    qty = Column(Integer, nullable=False, default=1, server_default="1")
    line_total = Column(Integer, nullable=False, default=0, server_default="0")

    order = relationship("LocalOrder", back_populates="items")
    options = relationship("LocalOrderItemOption", back_populates="order_item", cascade="all, delete-orphan")


class LocalOrderItemOption(Base):
    __tablename__ = "local_order_item_options"

    id = Column(Integer, primary_key=True, index=True)

    local_order_item_id = Column(Integer, ForeignKey("local_order_items.id", ondelete="CASCADE"), nullable=False, index=True)

    option_group_name = Column(String(120), nullable=False)
    option_value_name = Column(String(120), nullable=False)
    extra_price = Column(Integer, nullable=False, default=0, server_default="0")

    order_item = relationship("LocalOrderItem", back_populates="options")


# =========================================================
# RRHH
# =========================================================

class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)

    full_name = Column(String(150), nullable=False)
    cedula = Column(String(50), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(120), nullable=True)
    address = Column(Text, nullable=True)

    position = Column(String(80), nullable=True)
    salary_nio = Column(Float, nullable=True)

    hire_date = Column(DateTime(timezone=True), nullable=True)
    employment_status = Column(String(50), nullable=False, default="activo", server_default="activo")

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="employee_profiles")
    user = relationship("RestaurantUser", back_populates="employee_profile")

    vacation_balance = relationship("VacationBalance", back_populates="employee", uselist=False, cascade="all, delete-orphan")
    vacation_movements = relationship("VacationMovement", back_populates="employee", cascade="all, delete-orphan")
    liquidation_estimations = relationship("LiquidationEstimation", back_populates="employee", cascade="all, delete-orphan")


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    work_date = Column(String(20), nullable=False, index=True)
    check_in_at = Column(DateTime(timezone=True), nullable=True)
    check_out_at = Column(DateTime(timezone=True), nullable=True)

    worked_minutes = Column(Integer, nullable=True)
    created_by_pin = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="attendance_logs")


class VacationBalance(Base):
    __tablename__ = "vacation_balances"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_profile_id = Column(Integer, ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    accrued_days = Column(Float, nullable=False, default=0, server_default="0")
    used_days = Column(Float, nullable=False, default=0, server_default="0")
    available_days = Column(Float, nullable=False, default=0, server_default="0")

    last_recalculated_at = Column(DateTime(timezone=True), nullable=True)

    employee = relationship("EmployeeProfile", back_populates="vacation_balance")


class VacationMovement(Base):
    __tablename__ = "vacation_movements"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_profile_id = Column(Integer, ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    movement_type = Column(String(30), nullable=False)  # accrual / usage / adjustment
    days = Column(Float, nullable=False)

    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    employee = relationship("EmployeeProfile", back_populates="vacation_movements")


class LiquidationEstimation(Base):
    __tablename__ = "liquidation_estimations"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_profile_id = Column(Integer, ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False, index=True)

    calculation_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    years_worked = Column(Float, nullable=True)
    base_salary = Column(Float, nullable=True)
    estimated_amount_nio = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    employee = relationship("EmployeeProfile", back_populates="liquidation_estimations")


# =========================================================
# INVENTORY
# =========================================================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)
    contact_name = Column(String(120), nullable=True)
    ruc = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="suppliers")
    purchases = relationship("InventoryPurchaseHeader", back_populates="supplier")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(180), nullable=False)
    sku = Column(String(80), nullable=True, index=True)
    category = Column(String(120), nullable=True)
    unit_measure = Column(String(50), nullable=True)

    stock_current = Column(Float, nullable=False, default=0, server_default="0")
    stock_minimum = Column(Float, nullable=False, default=0, server_default="0")
    cost_avg = Column(Float, nullable=False, default=0, server_default="0")

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="inventory_items")
    purchase_items = relationship("InventoryPurchaseItem", back_populates="inventory_item")
    movements = relationship("InventoryMovement", back_populates="inventory_item", cascade="all, delete-orphan")
    recipes = relationship("ProductRecipe", back_populates="inventory_item", cascade="all, delete-orphan")


class InventoryPurchaseHeader(Base):
    __tablename__ = "inventory_purchase_headers"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    invoice_number = Column(String(100), nullable=False, index=True)
    purchase_date = Column(DateTime(timezone=True), nullable=True)

    currency = Column(String(10), nullable=True)
    exchange_rate_used = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="inventory_purchases")
    supplier = relationship("Supplier", back_populates="purchases")
    items = relationship("InventoryPurchaseItem", back_populates="purchase_header", cascade="all, delete-orphan")


class InventoryPurchaseItem(Base):
    __tablename__ = "inventory_purchase_items"

    id = Column(Integer, primary_key=True, index=True)

    purchase_header_id = Column(Integer, ForeignKey("inventory_purchase_headers.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True, index=True)

    qty = Column(Float, nullable=False, default=0, server_default="0")
    unit_cost = Column(Float, nullable=False, default=0, server_default="0")
    line_total = Column(Float, nullable=False, default=0, server_default="0")

    purchase_header = relationship("InventoryPurchaseHeader", back_populates="items")
    inventory_item = relationship("InventoryItem", back_populates="purchase_items")


class ProductRecipe(Base):
    __tablename__ = "product_recipes"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("menu_products.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)

    qty_required = Column(Float, nullable=False, default=0, server_default="0")
    unit_measure = Column(String(50), nullable=True)

    product = relationship("MenuProduct", back_populates="recipes")
    inventory_item = relationship("InventoryItem", back_populates="recipes")


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    movement_type = Column(String(50), nullable=False, index=True)
    source_type = Column(String(50), nullable=True)
    source_id = Column(Integer, nullable=True)

    reference_number = Column(String(100), nullable=True)

    qty_in = Column(Float, nullable=False, default=0, server_default="0")
    qty_out = Column(Float, nullable=False, default=0, server_default="0")
    balance_after = Column(Float, nullable=True)
    unit_cost = Column(Float, nullable=True)

    reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="inventory_movements")
    inventory_item = relationship("InventoryItem", back_populates="movements")


# =========================================================
# CASH / CLOSING
# =========================================================

class CashSession(Base):
    __tablename__ = "cash_sessions"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    opened_by_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    session_number = Column(String(100), nullable=False, unique=True, index=True)

    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    opening_fund_nio = Column(Float, nullable=False, default=0, server_default="0")
    opening_fund_usd = Column(Float, nullable=False, default=0, server_default="0")

    status = Column(String(20), nullable=False, default="open", server_default="open")
    notes = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="cash_sessions")
    movements = relationship("CashMovement", back_populates="cash_session", cascade="all, delete-orphan")
    closings = relationship("CashClosing", back_populates="cash_session", cascade="all, delete-orphan")


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    movement_type = Column(String(50), nullable=False, index=True)
    sales_channel = Column(String(20), nullable=True)  # delivery / pickup / local / combined
    currency = Column(String(10), nullable=True)       # NIO / USD
    amount = Column(Float, nullable=False, default=0, server_default="0")

    payment_method = Column(String(30), nullable=True)

    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)
    reference_number = Column(String(100), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="cash_movements")
    cash_session = relationship("CashSession", back_populates="movements")


class CashClosingTemplate(Base):
    __tablename__ = "cash_closing_templates"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    template_name = Column(String(120), nullable=False)
    header_text = Column(Text, nullable=True)
    footer_text = Column(Text, nullable=True)

    show_ruc = Column(Boolean, nullable=False, default=True, server_default="1")
    show_logo = Column(Boolean, nullable=False, default=True, server_default="1")
    is_default = Column(Boolean, nullable=False, default=False, server_default="0")

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="cash_closing_templates")


class CashClosing(Base):
    __tablename__ = "cash_closings"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    performed_by_user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    closing_number = Column(String(100), nullable=False, unique=True, index=True)
    closing_scope = Column(String(20), nullable=False)  # delivery / pickup / local / combined

    performed_by_name_snapshot = Column(String(150), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cash_sales_nio = Column(Float, nullable=False, default=0, server_default="0")
    cash_sales_usd = Column(Float, nullable=False, default=0, server_default="0")
    card_sales_nio = Column(Float, nullable=False, default=0, server_default="0")
    card_sales_usd = Column(Float, nullable=False, default=0, server_default="0")
    transfer_sales_nio = Column(Float, nullable=False, default=0, server_default="0")
    credit_sales_nio = Column(Float, nullable=False, default=0, server_default="0")

    tax_amount_nio = Column(Float, nullable=False, default=0, server_default="0")
    expenses_nio = Column(Float, nullable=False, default=0, server_default="0")

    opening_fund_nio = Column(Float, nullable=False, default=0, server_default="0")
    opening_fund_usd = Column(Float, nullable=False, default=0, server_default="0")

    counted_cash_nio = Column(Float, nullable=True)
    counted_cash_usd = Column(Float, nullable=True)

    difference_nio = Column(Float, nullable=True)
    difference_usd = Column(Float, nullable=True)

    preview_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="cash_closings")
    cash_session = relationship("CashSession", back_populates="closings")


# =========================================================
# ANALYTICS
# =========================================================

class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "metric_date", name="uq_daily_metric"),
    )

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)

    metric_date = Column(String(20), nullable=False, index=True)

    delivery_orders_count = Column(Integer, nullable=False, default=0, server_default="0")
    pickup_orders_count = Column(Integer, nullable=False, default=0, server_default="0")
    local_orders_count = Column(Integer, nullable=False, default=0, server_default="0")

    delivery_sales_total = Column(Float, nullable=False, default=0, server_default="0")
    pickup_sales_total = Column(Float, nullable=False, default=0, server_default="0")
    local_sales_total = Column(Float, nullable=False, default=0, server_default="0")
    combined_sales_total = Column(Float, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="daily_metrics")


class ProductSalesMetric(Base):
    __tablename__ = "product_sales_metrics"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("menu_products.id", ondelete="SET NULL"), nullable=True, index=True)

    metric_date = Column(String(20), nullable=False, index=True)
    sales_channel = Column(String(20), nullable=True)

    qty_sold = Column(Float, nullable=False, default=0, server_default="0")
    revenue_total = Column(Float, nullable=False, default=0, server_default="0")
    cost_estimated = Column(Float, nullable=False, default=0, server_default="0")
    margin_estimated = Column(Float, nullable=False, default=0, server_default="0")

    restaurant = relationship("Restaurant", back_populates="product_sales_metrics")


class UserSalesMetric(Base):
    __tablename__ = "user_sales_metrics"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    metric_date = Column(String(20), nullable=False, index=True)
    sales_channel = Column(String(20), nullable=True)

    orders_count = Column(Integer, nullable=False, default=0, server_default="0")
    items_sold = Column(Float, nullable=False, default=0, server_default="0")
    revenue_total = Column(Float, nullable=False, default=0, server_default="0")
    margin_estimated = Column(Float, nullable=False, default=0, server_default="0")

    restaurant = relationship("Restaurant", back_populates="user_sales_metrics")


class DriverMetric(Base):
    __tablename__ = "driver_metrics"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True)

    metric_date = Column(String(20), nullable=False, index=True)

    orders_delivered = Column(Integer, nullable=False, default=0, server_default="0")
    distance_km = Column(Float, nullable=False, default=0, server_default="0")
    revenue_related = Column(Float, nullable=False, default=0, server_default="0")

    restaurant = relationship("Restaurant", back_populates="driver_metrics")


# =========================================================
# EXPORTS
# =========================================================

class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("restaurant_users.id", ondelete="SET NULL"), nullable=True, index=True)

    module_code = Column(String(50), nullable=False)
    export_type = Column(String(50), nullable=False)

    date_from = Column(String(20), nullable=True)
    date_to = Column(String(20), nullable=True)

    file_format = Column(String(20), nullable=False)  # xlsx / docx / pdf / csv
    file_path = Column(Text, nullable=True)

    status = Column(String(30), nullable=False, default="pending", server_default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="exports")
