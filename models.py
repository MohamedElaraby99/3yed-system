from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
import uuid
import qrcode
import io
import base64
from PIL import Image

db = SQLAlchemy()

# جدول الأدوار والصلاحيات
class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    name_ar = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    permissions = db.Column(db.JSON)  # قائمة بالصلاحيات
    
    users = db.relationship('User', backref='user_role', lazy='dynamic')

# جدول المستخدمين
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(20))
    
    # معلومات الوظيفة
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    employee_id = db.Column(db.String(20), unique=True)
    salary = db.Column(db.Float)
    hire_date = db.Column(db.Date, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # QR للحضور والانصراف
    current_qr_token = db.Column(db.String(255))
    qr_expiry = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    attendance_records = db.relationship('Attendance', backref='employee', lazy='dynamic')
    orders = db.relationship('Order', backref='cashier', lazy='dynamic')
    
    def generate_attendance_qr(self):
        """توليد QR جديد للحضور والانصراف"""
        self.current_qr_token = str(uuid.uuid4())
        self.qr_expiry = datetime.utcnow() + timedelta(hours=24)
        
        qr_data = f"attendance:{self.id}:{self.current_qr_token}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode()
    
    def is_qr_valid(self):
        """التحقق من صحة QR"""
        return self.qr_expiry and datetime.utcnow() < self.qr_expiry

# جدول حضور الموظفين
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    total_hours = db.Column(db.Float)
    status = db.Column(db.String(20), default='absent')  # present, absent, late, early_leave
    notes = db.Column(db.Text)
    
    def calculate_hours(self):
        """حساب ساعات العمل"""
        if self.check_in and self.check_out:
            delta = self.check_out - self.check_in
            self.total_hours = delta.total_seconds() / 3600

# جدول الغرف
class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    hourly_rate = db.Column(db.Float, nullable=False)
    amenities = db.Column(db.JSON)  # قائمة بالمرافق
    is_available = db.Column(db.Boolean, default=True)
    qr_code = db.Column(db.String(255), unique=True)
    
    # العلاقات
    bookings = db.relationship('Booking', backref='room', lazy='dynamic')
    
    def __init__(self, **kwargs):
        super(Room, self).__init__(**kwargs)
        self.qr_code = str(uuid.uuid4())
    
    def generate_menu_qr(self):
        """توليد QR للمنيو"""
        qr_data = f"http://room{self.id}.fikracafe.com"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode()

# جدول حجوزات الغرف
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    total_hours = db.Column(db.Float)
    total_cost = db.Column(db.Float)
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled
    session_id = db.Column(db.String(255), unique=True)
    
    # العلاقات
    orders = db.relationship('Order', backref='booking', lazy='dynamic')
    
    def __init__(self, **kwargs):
        super(Booking, self).__init__(**kwargs)
        self.session_id = str(uuid.uuid4())
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            self.total_hours = delta.total_seconds() / 3600
            if hasattr(self, 'room') and self.room:
                self.total_cost = self.total_hours * self.room.hourly_rate

# جدول فئات المنتجات
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    name_ar = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    # العلاقات
    products = db.relationship('Product', backref='category', lazy='dynamic')

# جدول المنتجات
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    name_ar = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    image_url = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True)
    preparation_time = db.Column(db.Integer, default=5)  # بالدقائق
    
    # إدارة المخزون
    stock_quantity = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=5)
    unit = db.Column(db.String(20), default='piece')
    
    # العلاقات
    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')

# جدول الطلبات
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'))
    cashier_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # تفاصيل الطلب
    subtotal = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)
    
    # معلومات الدفع
    payment_method = db.Column(db.String(20))  # cash, card, wallet
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, cancelled
    
    # معلومات الطلب
    status = db.Column(db.String(20), default='pending')  # pending, preparing, ready, delivered, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # العلاقات
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(Order, self).__init__(**kwargs)
        if not self.order_number:
            self.order_number = f"ORD{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
    
    def calculate_total(self):
        """حساب إجمالي الطلب"""
        self.subtotal = sum(item.total_price for item in self.items)
        self.tax_amount = self.subtotal * 0.15  # ضريبة القيمة المضافة 15%
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount

# جدول عناصر الطلب
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)  # ملاحظات خاصة بالعنصر
    
    def __init__(self, **kwargs):
        super(OrderItem, self).__init__(**kwargs)
        if self.unit_price and self.quantity:
            self.total_price = self.unit_price * self.quantity

# جدول المخزون
class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # purchase, sale, adjustment, waste
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float)
    total_cost = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # العلاقات
    product = db.relationship('Product', backref='inventory_transactions')
    user = db.relationship('User', backref='inventory_transactions')

# جدول التقييمات
class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'))
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    booking = db.relationship('Booking', backref='rating')

# جدول العروض والخصومات
class Discount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)  # percentage, fixed
    discount_value = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0)
    max_discount_amount = db.Column(db.Float)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    usage_limit = db.Column(db.Integer)
    usage_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    def is_valid(self):
        """التحقق من صحة الكوبون"""
        now = datetime.utcnow()
        return (self.is_active and 
                self.start_date <= now <= self.end_date and 
                (self.usage_limit is None or self.usage_count < self.usage_limit))

# إنشاء البيانات الأولية
def create_default_data():
    """إنشاء البيانات الافتراضية"""
    
    # الأدوار الافتراضية
    roles_data = [
        {
            'name': 'admin',
            'name_ar': 'مدير عام',
            'description': 'صلاحيات كاملة',
            'permissions': ['all']
        },
        {
            'name': 'manager',
            'name_ar': 'مدير',
            'description': 'إدارة العمليات اليومية',
            'permissions': ['manage_staff', 'view_reports', 'manage_bookings', 'manage_inventory']
        },
        {
            'name': 'bar_manager',
            'name_ar': 'مدير بار',
            'description': 'إدارة البار والمخزون',
            'permissions': ['manage_orders', 'manage_inventory', 'view_bar_reports']
        },
        {
            'name': 'cashier',
            'name_ar': 'كاشير',
            'description': 'معالجة الطلبات والمدفوعات',
            'permissions': ['process_orders', 'handle_payments']
        },
        {
            'name': 'receptionist',
            'name_ar': 'موظف استقبال',
            'description': 'حجز الغرف وتسجيل الحضور',
            'permissions': ['manage_bookings', 'record_attendance']
        },
        {
            'name': 'hr',
            'name_ar': 'موارد بشرية',
            'description': 'إدارة الموظفين والحضور',
            'permissions': ['manage_staff', 'view_attendance', 'manage_payroll']
        },
        {
            'name': 'accountant',
            'name_ar': 'محاسب',
            'description': 'عرض التقارير المالية فقط',
            'permissions': ['view_financial_reports']
        }
    ]
    
    for role_data in roles_data:
        if not Role.query.filter_by(name=role_data['name']).first():
            role = Role(**role_data)
            db.session.add(role)
    
    # فئات المنتجات الافتراضية
    categories_data = [
        {
            'name': 'Hot Drinks',
            'name_ar': 'مشروبات ساخنة',
            'description': 'قهوة وشاي وشوكولاتة ساخنة',
            'sort_order': 1
        },
        {
            'name': 'Cold Drinks',
            'name_ar': 'مشروبات باردة',
            'description': 'عصائر طبيعية ومشروبات منعشة',
            'sort_order': 2
        },
        {
            'name': 'Desserts',
            'name_ar': 'حلويات',
            'description': 'كيك وبسكويت وحلويات متنوعة',
            'sort_order': 3
        },
        {
            'name': 'Snacks',
            'name_ar': 'سناكس',
            'description': 'ساندويتشات ومعجنات خفيفة',
            'sort_order': 4
        }
    ]
    
    for cat_data in categories_data:
        if not Category.query.filter_by(name=cat_data['name']).first():
            category = Category(**cat_data)
            db.session.add(category)
    
    # غرف افتراضية
    rooms_data = [
        {
            'name': 'غرفة اجتماعات A',
            'capacity': 8,
            'hourly_rate': 50.0,
            'amenities': ['واي فاي', 'بروجيكتور', 'سبورة']
        },
        {
            'name': 'غرفة اجتماعات B',
            'capacity': 6,
            'hourly_rate': 40.0,
            'amenities': ['واي فاي', 'تلفزيون']
        },
        {
            'name': 'مكتب خاص',
            'capacity': 2,
            'hourly_rate': 30.0,
            'amenities': ['واي فاي', 'مكتب']
        }
    ]
    
    for room_data in rooms_data:
        if not Room.query.filter_by(name=room_data['name']).first():
            room = Room(**room_data)
            db.session.add(room)
    
    db.session.commit() 