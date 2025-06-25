from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_
from models import db, User, Role, Order, Booking, Room, Product, Category, Attendance

dashboard_bp = Blueprint('dashboard', __name__)

def has_permission(permission):
    """تحقق من وجود صلاحية معينة للمستخدم الحالي"""
    if not current_user.is_authenticated:
        return False
    
    user_permissions = current_user.user_role.permissions or []
    return 'all' in user_permissions or permission in user_permissions

@dashboard_bp.route('/')
@login_required
def main():
    """لوحة التحكم الرئيسية"""
    today = date.today()
    
    # إحصائيات عامة
    stats = {}
    
    # مبيعات اليوم
    today_orders = Order.query.filter(
        func.date(Order.created_at) == today,
        Order.payment_status == 'paid'
    ).all()
    stats['today_sales'] = sum(order.total_amount for order in today_orders)
    stats['today_orders_count'] = len(today_orders)
    
    # حجوزات اليوم
    today_bookings = Booking.query.filter(
        func.date(Booking.start_time) == today
    ).all()
    stats['today_bookings'] = len(today_bookings)
    
    # الحضور اليوم
    today_attendance = Attendance.query.filter(
        Attendance.date == today,
        Attendance.status == 'present'
    ).count()
    stats['today_attendance'] = today_attendance
    
    # الغرف المتاحة
    available_rooms = Room.query.filter_by(is_available=True).count()
    stats['available_rooms'] = available_rooms
    
    # طلبات قيد التحضير
    pending_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing'])
    ).count()
    stats['pending_orders'] = pending_orders
    
    # منتجات قليلة المخزون
    low_stock_products = Product.query.filter(
        Product.stock_quantity <= Product.min_stock_level
    ).count()
    stats['low_stock_products'] = low_stock_products
    
    # أحدث الطلبات
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    # أحدث الحجوزات
    recent_bookings = Booking.query.order_by(Booking.start_time.desc()).limit(5).all()
    
    # إحصائيات المبيعات الأسبوعية
    week_ago = today - timedelta(days=7)
    weekly_sales = []
    for i in range(7):
        check_date = week_ago + timedelta(days=i)
        day_orders = Order.query.filter(
            func.date(Order.created_at) == check_date,
            Order.payment_status == 'paid'
        ).all()
        day_total = sum(order.total_amount for order in day_orders)
        weekly_sales.append({
            'date': check_date.strftime('%Y-%m-%d'),
            'total': day_total
        })
    
    return render_template('dashboard/main.html', 
                         stats=stats,
                         recent_orders=recent_orders,
                         recent_bookings=recent_bookings,
                         weekly_sales=weekly_sales,
                         has_permission=has_permission)

@dashboard_bp.route('/stats/api')
@login_required
def stats_api():
    """API للإحصائيات المباشرة"""
    today = date.today()
    
    # مبيعات اليوم
    today_sales = db.session.query(func.sum(Order.total_amount)).filter(
        func.date(Order.created_at) == today,
        Order.payment_status == 'paid'
    ).scalar() or 0
    
    # عدد الطلبات قيد التحضير
    pending_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing'])
    ).count()
    
    # الغرف المحجوزة حالياً
    current_time = datetime.now()
    active_bookings = Booking.query.filter(
        and_(
            Booking.start_time <= current_time,
            Booking.end_time >= current_time,
            Booking.status == 'active'
        )
    ).count()
    
    return jsonify({
        'today_sales': float(today_sales),
        'pending_orders': pending_orders,
        'active_bookings': active_bookings,
        'timestamp': datetime.now().isoformat()
    })

@dashboard_bp.route('/owner')
@login_required
def owner_dashboard():
    """لوحة تحكم المالك"""
    if not has_permission('view_financial_reports'):
        return render_template('errors/403.html'), 403
    
    # إحصائيات مالية شاملة
    today = date.today()
    month_start = today.replace(day=1)
    
    # إيرادات الشهر
    monthly_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.created_at >= month_start,
        Order.payment_status == 'paid'
    ).scalar() or 0
    
    # إيرادات الحجوزات
    booking_revenue = db.session.query(func.sum(Booking.total_cost)).filter(
        Booking.start_time >= month_start,
        Booking.status != 'cancelled'
    ).scalar() or 0
    
    # أفضل المنتجات مبيعاً
    from sqlalchemy import desc
    top_products = db.session.query(
        Product.name_ar,
        func.sum(Order.items.c.quantity).label('total_sold'),
        func.sum(Order.items.c.total_price).label('total_revenue')
    ).join(Order.items).filter(
        Order.created_at >= month_start,
        Order.payment_status == 'paid'
    ).group_by(Product.id).order_by(desc('total_sold')).limit(10).all()
    
    return render_template('dashboard/owner.html',
                         monthly_revenue=monthly_revenue,
                         booking_revenue=booking_revenue,
                         top_products=top_products,
                         has_permission=has_permission)

@dashboard_bp.route('/manager')
@login_required  
def manager_dashboard():
    """لوحة تحكم المدير"""
    if not has_permission('manage_staff'):
        return render_template('errors/403.html'), 403
    
    today = date.today()
    
    # إحصائيات الموظفين
    total_employees = User.query.filter_by(is_active=True).count()
    present_today = Attendance.query.filter(
        Attendance.date == today,
        Attendance.status == 'present'
    ).count()
    
    # الحجوزات اليوم
    today_bookings = Booking.query.filter(
        func.date(Booking.start_time) == today
    ).all()
    
    # تنبيهات المخزون
    low_stock_items = Product.query.filter(
        Product.stock_quantity <= Product.min_stock_level
    ).all()
    
    return render_template('dashboard/manager.html',
                         total_employees=total_employees,
                         present_today=present_today,
                         today_bookings=today_bookings,
                         low_stock_items=low_stock_items,
                         has_permission=has_permission)

@dashboard_bp.route('/bar')
@login_required
def bar_dashboard():
    """لوحة تحكم البار"""
    if not has_permission('manage_orders'):
        return render_template('errors/403.html'), 403
    
    # الطلبات الحية
    live_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing'])
    ).order_by(Order.created_at.asc()).all()
    
    # طلبات جاهزة للتسليم
    ready_orders = Order.query.filter_by(status='ready').all()
    
    # إحصائيات اليوم
    today = date.today()
    today_orders = Order.query.filter(
        func.date(Order.created_at) == today
    ).all()
    
    return render_template('dashboard/bar.html',
                         live_orders=live_orders,
                         ready_orders=ready_orders,
                         today_orders=today_orders,
                         has_permission=has_permission) 