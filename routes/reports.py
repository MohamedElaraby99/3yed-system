from flask import Blueprint, render_template, request, jsonify, make_response
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from models import db, Order, OrderItem, Product, Category, Booking, Room, User, Attendance
from sqlalchemy import func, and_
import csv
import io

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/')
@login_required
def index():
    """صفحة التقارير الرئيسية"""
    return render_template('reports/index.html')

@reports_bp.route('/sales')
@login_required
def sales_report():
    """تقرير المبيعات"""
    # فلاتر التقرير
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # تعيين تواريخ افتراضية (آخر 30 يوم)
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')
    
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # استعلام المبيعات
    sales_data = db.session.query(
        func.date(Order.created_at).label('date'),
        func.count(Order.id).label('orders_count'),
        func.sum(Order.total_amount).label('total_sales'),
        func.avg(Order.total_amount).label('avg_order_value')
    ).filter(
        and_(
            Order.created_at >= start_datetime,
            Order.created_at < end_datetime,
            Order.payment_status == 'paid'
        )
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
    
    # أفضل المنتجات مبيعاً
    top_products = db.session.query(
        Product.name_ar,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.total_price).label('revenue')
    ).join(OrderItem).join(Order).filter(
        and_(
            Order.created_at >= start_datetime,
            Order.created_at < end_datetime,
            Order.payment_status == 'paid'
        )
    ).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(10).all()
    
    # تقسيم المبيعات حسب طرق الدفع
    payment_methods = db.session.query(
        Order.payment_method,
        func.sum(Order.total_amount).label('total'),
        func.count(Order.id).label('count')
    ).filter(
        and_(
            Order.created_at >= start_datetime,
            Order.created_at < end_datetime,
            Order.payment_status == 'paid'
        )
    ).group_by(Order.payment_method).all()
    
    # إجمالي المبيعات
    total_sales = sum(row.total_sales or 0 for row in sales_data)
    total_orders = sum(row.orders_count for row in sales_data)
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    return render_template('reports/sales.html',
                         sales_data=sales_data,
                         top_products=top_products,
                         payment_methods=payment_methods,
                         total_sales=total_sales,
                         total_orders=total_orders,
                         avg_order_value=avg_order_value,
                         start_date=start_date,
                         end_date=end_date)

@reports_bp.route('/bookings')
@login_required
def bookings_report():
    """تقرير الحجوزات"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')
    
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # إحصائيات الحجوزات
    bookings_stats = db.session.query(
        func.date(Booking.start_time).label('date'),
        func.count(Booking.id).label('bookings_count'),
        func.sum(Booking.total_cost).label('total_revenue'),
        func.sum(Booking.total_hours).label('total_hours')
    ).filter(
        and_(
            Booking.start_time >= start_datetime,
            Booking.start_time < end_datetime,
            Booking.status != 'cancelled'
        )
    ).group_by(func.date(Booking.start_time)).order_by(func.date(Booking.start_time)).all()
    
    # أداء الغرف
    room_performance = db.session.query(
        Room.name,
        func.count(Booking.id).label('bookings_count'),
        func.sum(Booking.total_cost).label('revenue'),
        func.sum(Booking.total_hours).label('hours_booked')
    ).join(Booking).filter(
        and_(
            Booking.start_time >= start_datetime,
            Booking.start_time < end_datetime,
            Booking.status != 'cancelled'
        )
    ).group_by(Room.id).order_by(func.sum(Booking.total_cost).desc()).all()
    
    # إجماليات
    total_bookings = sum(row.bookings_count for row in bookings_stats)
    total_revenue = sum(row.total_revenue or 0 for row in bookings_stats)
    total_hours = sum(row.total_hours or 0 for row in bookings_stats)
    
    return render_template('reports/bookings.html',
                         bookings_stats=bookings_stats,
                         room_performance=room_performance,
                         total_bookings=total_bookings,
                         total_revenue=total_revenue,
                         total_hours=total_hours,
                         start_date=start_date,
                         end_date=end_date)

@reports_bp.route('/attendance')
@login_required
def attendance_report():
    """تقرير الحضور"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')
    
    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # إحصائيات الحضور لكل موظف
    employee_stats = db.session.query(
        User.first_name,
        User.last_name,
        func.count(Attendance.id).label('total_days'),
        func.sum(func.case([(Attendance.status == 'present', 1)], else_=0)).label('present_days'),
        func.sum(func.case([(Attendance.status == 'absent', 1)], else_=0)).label('absent_days'),
        func.sum(Attendance.total_hours).label('total_hours')
    ).join(Attendance).filter(
        and_(
            Attendance.date >= start_date_obj,
            Attendance.date <= end_date_obj
        )
    ).group_by(User.id).all()
    
    # إحصائيات يومية
    daily_stats = db.session.query(
        Attendance.date,
        func.count(Attendance.id).label('total_employees'),
        func.sum(func.case([(Attendance.status == 'present', 1)], else_=0)).label('present_count'),
        func.avg(Attendance.total_hours).label('avg_hours')
    ).filter(
        and_(
            Attendance.date >= start_date_obj,
            Attendance.date <= end_date_obj
        )
    ).group_by(Attendance.date).order_by(Attendance.date).all()
    
    return render_template('reports/attendance.html',
                         employee_stats=employee_stats,
                         daily_stats=daily_stats,
                         start_date=start_date,
                         end_date=end_date)

@reports_bp.route('/financial')
@login_required
def financial_report():
    """التقرير المالي الشامل"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = date.today().replace(day=1).strftime('%Y-%m-%d')  # بداية الشهر
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')
    
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # إيرادات المبيعات
    sales_revenue = db.session.query(
        func.sum(Order.total_amount)
    ).filter(
        and_(
            Order.created_at >= start_datetime,
            Order.created_at < end_datetime,
            Order.payment_status == 'paid'
        )
    ).scalar() or 0
    
    # إيرادات الحجوزات
    booking_revenue = db.session.query(
        func.sum(Booking.total_cost)
    ).filter(
        and_(
            Booking.start_time >= start_datetime,
            Booking.start_time < end_datetime,
            Booking.status != 'cancelled'
        )
    ).scalar() or 0
    
    # تكاليف المشتريات (إذا كانت متوفرة)
    purchase_costs = db.session.query(
        func.sum(Inventory.total_cost)
    ).filter(
        and_(
            Inventory.created_at >= start_datetime,
            Inventory.created_at < end_datetime,
            Inventory.transaction_type == 'purchase'
        )
    ).scalar() or 0
    
    # إجمالي الإيرادات
    total_revenue = sales_revenue + booking_revenue
    
    # الربح التقديري (الإيرادات - تكاليف المشتريات)
    estimated_profit = total_revenue - purchase_costs
    
    # تفصيل الإيرادات اليومية
    daily_revenue = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(Order.total_amount).label('sales'),
        func.sum(Booking.total_cost).label('bookings')
    ).outerjoin(
        Booking, func.date(Order.created_at) == func.date(Booking.start_time)
    ).filter(
        and_(
            Order.created_at >= start_datetime,
            Order.created_at < end_datetime,
            Order.payment_status == 'paid'
        )
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
    
    return render_template('reports/financial.html',
                         sales_revenue=sales_revenue,
                         booking_revenue=booking_revenue,
                         purchase_costs=purchase_costs,
                         total_revenue=total_revenue,
                         estimated_profit=estimated_profit,
                         daily_revenue=daily_revenue,
                         start_date=start_date,
                         end_date=end_date)

@reports_bp.route('/export/sales-csv')
@login_required
def export_sales_csv():
    """تصدير تقرير المبيعات إلى CSV"""
    start_date = request.args.get('start_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # استعلام بيانات المبيعات
    orders = db.session.query(Order, OrderItem, Product).join(
        OrderItem
    ).join(Product).filter(
        and_(
            Order.created_at >= start_datetime,
            Order.created_at < end_datetime,
            Order.payment_status == 'paid'
        )
    ).order_by(Order.created_at.desc()).all()
    
    # إنشاء ملف CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # رؤوس الأعمدة
    writer.writerow([
        'رقم الطلب', 'التاريخ', 'المنتج', 'الكمية', 
        'سعر الوحدة', 'الإجمالي', 'طريقة الدفع'
    ])
    
    # البيانات
    for order, item, product in orders:
        writer.writerow([
            order.order_number,
            order.created_at.strftime('%Y-%m-%d %H:%M'),
            product.name_ar,
            item.quantity,
            item.unit_price,
            item.total_price,
            order.payment_method or 'غير محدد'
        ])
    
    # إعداد الاستجابة
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=sales_report_{start_date}_to_{end_date}.csv'
    
    return response

@reports_bp.route('/api/dashboard-stats')
@login_required
def dashboard_stats_api():
    """API للإحصائيات المباشرة للوحة التحكم"""
    today = date.today()
    
    # مبيعات اليوم
    today_sales = db.session.query(func.sum(Order.total_amount)).filter(
        func.date(Order.created_at) == today,
        Order.payment_status == 'paid'
    ).scalar() or 0
    
    # طلبات اليوم
    today_orders = Order.query.filter(
        func.date(Order.created_at) == today
    ).count()
    
    # حجوزات اليوم
    today_bookings = Booking.query.filter(
        func.date(Booking.start_time) == today
    ).count()
    
    # موظفين حاضرين اليوم
    present_employees = Attendance.query.filter(
        Attendance.date == today,
        Attendance.status == 'present'
    ).count()
    
    return jsonify({
        'today_sales': float(today_sales),
        'today_orders': today_orders,
        'today_bookings': today_bookings,
        'present_employees': present_employees,
        'timestamp': datetime.now().isoformat()
    }) 