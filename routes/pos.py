from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Order, OrderItem, Product, Category, Booking, Room
from sqlalchemy import func

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/')
@login_required
def index():
    """واجهة نقطة البيع الرئيسية"""
    from datetime import date
    from sqlalchemy import func
    
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    products = Product.query.filter_by(is_available=True).all()
    
    # الطلبات النشطة
    active_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing', 'ready'])
    ).order_by(Order.created_at.desc()).all()
    
    # إحصائيات اليوم
    today = date.today()
    
    # مبيعات اليوم
    today_orders = Order.query.filter(
        func.date(Order.created_at) == today,
        Order.payment_status == 'paid'
    ).all()
    daily_sales = sum(order.total_amount for order in today_orders)
    daily_orders = len(today_orders)
    
    # طلبات قيد التحضير
    pending_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing'])
    ).count()
    
    # متوسط قيمة الطلب
    avg_order = daily_sales / daily_orders if daily_orders > 0 else 0
    
    # الغرف للحجوزات
    rooms = Room.query.filter_by(is_available=True).all()
    
    # رقم الطلب التالي
    order_number = f"ORD{datetime.now().strftime('%Y%m%d')}{Order.query.count() + 1:03d}"
    
    return render_template('pos/index.html', 
                         categories=categories,
                         products=products,
                         active_orders=active_orders,
                         daily_sales=daily_sales,
                         daily_orders=daily_orders,
                         pending_orders=pending_orders,
                         avg_order=avg_order,
                         rooms=rooms,
                         order_number=order_number)

@pos_bp.route('/create_order', methods=['POST'])
@login_required
def create_order():
    """إنشاء طلب جديد من واجهة POS"""
    try:
        # الحصول على البيانات من النموذج
        customer_name = request.form.get('customer_name', '')
        room_id = request.form.get('room_id')
        payment_method = request.form.get('payment_method', 'cash')
        notes = request.form.get('notes', '')
        cart_items = request.form.get('cart_items')
        total_amount = float(request.form.get('total_amount', 0))
        
        if cart_items:
            import json
            cart_items = json.loads(cart_items)
        else:
            return jsonify({'success': False, 'message': 'لا توجد عناصر في السلة'})
        
        # إنشاء الطلب
        order = Order(
            user_id=current_user.id,
            customer_name=customer_name,
            room_id=room_id if room_id else None,
            payment_method=payment_method,
            payment_status='paid',
            status='pending',
            notes=notes
        )
        
        db.session.add(order)
        db.session.flush()  # للحصول على ID الطلب
        
        subtotal = 0
        
        # إضافة عناصر الطلب
        for product_id, item_data in cart_items.items():
            product = Product.query.get(int(product_id))
            if not product or not product.is_available:
                return jsonify({'success': False, 'message': f'المنتج غير متوفر'})
            
            # التحقق من المخزون
            if product.stock_quantity < item_data['quantity']:
                return jsonify({'success': False, 'message': f'مخزون غير كافي للمنتج: {product.name_ar}'})
            
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item_data['quantity'],
                price=product.price,
                total_price=product.price * item_data['quantity']
            )
            
            db.session.add(order_item)
            subtotal += order_item.total_price
            
            # خصم من المخزون
            product.stock_quantity -= item_data['quantity']
        
        # حساب الإجمالي مع الضريبة
        order.subtotal = subtotal
        order.tax_amount = subtotal * 0.15  # ضريبة القيمة المضافة
        order.total_amount = order.subtotal + order.tax_amount
        
        db.session.commit()
        
        # رقم الطلب التالي
        next_order_number = f"ORD{datetime.now().strftime('%Y%m%d')}{Order.query.count() + 1:03d}"
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'total_amount': order.total_amount,
            'next_order_number': next_order_number
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@pos_bp.route('/new-order', methods=['POST'])
@login_required
def new_order():
    """إنشاء طلب جديد"""
    try:
        data = request.get_json()
        
        # إنشاء الطلب
        order = Order(
            cashier_id=current_user.id,
            booking_id=data.get('booking_id'),
            notes=data.get('notes', '')
        )
        
        db.session.add(order)
        db.session.flush()  # للحصول على ID الطلب
        
        total_amount = 0
        
        # إضافة عناصر الطلب
        for item_data in data.get('items', []):
            product = Product.query.get(item_data['product_id'])
            if not product or not product.is_available:
                return jsonify({'success': False, 'message': f'المنتج غير متوفر: {item_data["product_id"]}'})
            
            # التحقق من المخزون
            if product.stock_quantity < item_data['quantity']:
                return jsonify({'success': False, 'message': f'مخزون غير كافي للمنتج: {product.name_ar}'})
            
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item_data['quantity'],
                unit_price=product.price,
                notes=item_data.get('notes', '')
            )
            
            db.session.add(order_item)
            total_amount += order_item.total_price
            
            # خصم من المخزون
            product.stock_quantity -= item_data['quantity']
        
        # حساب الإجمالي مع الضريبة
        order.subtotal = total_amount
        order.tax_amount = total_amount * 0.15  # ضريبة القيمة المضافة
        order.discount_amount = data.get('discount_amount', 0)
        order.total_amount = order.subtotal + order.tax_amount - order.discount_amount
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'total_amount': order.total_amount
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@pos_bp.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    """تفاصيل الطلب"""
    order = Order.query.get_or_404(order_id)
    return render_template('pos/order_details.html', order=order)

@pos_bp.route('/update_status/<int:order_id>', methods=['POST'])
@login_required
def update_status(order_id):
    """تحديث حالة الطلب"""
    try:
        order = Order.query.get_or_404(order_id)
        data = request.get_json()
        new_status = data.get('status')
        
        valid_statuses = ['pending', 'preparing', 'ready', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'message': 'حالة غير صحيحة'})
        
        order.status = new_status
        
        if new_status in ['delivered', 'cancelled']:
            order.completed_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم تحديث حالة الطلب إلى: {new_status}'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@pos_bp.route('/order/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_order_status(order_id):
    """تحديث حالة الطلب"""
    order = Order.query.get_or_404(order_id)
    new_status = request.json.get('status')
    
    valid_statuses = ['pending', 'preparing', 'ready', 'delivered', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({'success': False, 'message': 'حالة غير صحيحة'})
    
    order.status = new_status
    
    if new_status in ['delivered', 'cancelled']:
        order.completed_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'تم تحديث حالة الطلب إلى: {new_status}'
    })

@pos_bp.route('/order/<int:order_id>/payment', methods=['POST'])
@login_required
def process_payment(order_id):
    """معالجة الدفع"""
    order = Order.query.get_or_404(order_id)
    
    payment_method = request.json.get('payment_method')
    valid_methods = ['cash', 'card', 'wallet']
    
    if payment_method not in valid_methods:
        return jsonify({'success': False, 'message': 'طريقة دفع غير صحيحة'})
    
    order.payment_method = payment_method
    order.payment_status = 'paid'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'تم الدفع بنجاح',
        'receipt_url': url_for('pos.print_receipt', order_id=order.id)
    })

@pos_bp.route('/order/<int:order_id>/receipt')
@login_required
def print_receipt(order_id):
    """طباعة الفاتورة"""
    order = Order.query.get_or_404(order_id)
    return render_template('pos/receipt.html', order=order)

@pos_bp.route('/products/search')
@login_required
def search_products():
    """البحث في المنتجات"""
    query = request.args.get('q', '')
    category_id = request.args.get('category_id')
    
    products_query = Product.query.filter_by(is_available=True)
    
    if query:
        products_query = products_query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.name_ar.ilike(f'%{query}%')
            )
        )
    
    if category_id:
        products_query = products_query.filter_by(category_id=category_id)
    
    products = products_query.all()
    
    return jsonify({
        'products': [{
            'id': p.id,
            'name': p.name_ar,
            'price': p.price,
            'stock_quantity': p.stock_quantity,
            'image_url': p.image_url
        } for p in products]
    })

@pos_bp.route('/orders/live')
@login_required
def live_orders():
    """الطلبات المباشرة للمطبخ/البار"""
    live_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing'])
    ).order_by(Order.created_at.asc()).all()
    
    return render_template('pos/live_orders.html', orders=live_orders)

@pos_bp.route('/orders_count')
@login_required
def orders_count():
    """عدد الطلبات الحالية"""
    count = Order.query.filter(
        Order.status.in_(['pending', 'preparing', 'ready'])
    ).count()
    
    return jsonify({'count': count})

@pos_bp.route('/sales-summary')
@login_required
def sales_summary():
    """ملخص المبيعات اليومية"""
    today = datetime.now().date()
    
    # مبيعات اليوم
    today_orders = Order.query.filter(
        func.date(Order.created_at) == today,
        Order.payment_status == 'paid'
    ).all()
    
    total_sales = sum(order.total_amount for order in today_orders)
    total_orders = len(today_orders)
    
    # تفاصيل طرق الدفع
    payment_breakdown = {}
    for order in today_orders:
        method = order.payment_method or 'غير محدد'
        payment_breakdown[method] = payment_breakdown.get(method, 0) + order.total_amount
    
    # أفضل المنتجات مبيعاً
    top_products = db.session.query(
        Product.name_ar,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.total_price).label('revenue')
    ).join(OrderItem).join(Order).filter(
        func.date(Order.created_at) == today,
        Order.payment_status == 'paid'
    ).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(10).all()
    
    return render_template('pos/sales_summary.html',
                         total_sales=total_sales,
                         total_orders=total_orders,
                         payment_breakdown=payment_breakdown,
                         top_products=top_products)

@pos_bp.route('/api/order-status/<int:order_id>')
@login_required
def get_order_status(order_id):
    """API للحصول على حالة الطلب"""
    order = Order.query.get_or_404(order_id)
    
    return jsonify({
        'id': order.id,
        'order_number': order.order_number,
        'status': order.status,
        'payment_status': order.payment_status,
        'total_amount': float(order.total_amount),
        'created_at': order.created_at.isoformat(),
        'items_count': order.items.count()
    }) 