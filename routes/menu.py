from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime
from models import db, Product, Category, Order, OrderItem, Booking, Room
import uuid

menu_bp = Blueprint('menu', __name__)

@menu_bp.route('/room/<string:room_qr>')
def room_menu(room_qr):
    """عرض المنيو للعملاء عبر QR الغرفة"""
    # البحث عن الغرفة بناءً على QR code
    room = Room.query.filter_by(qr_code=room_qr).first()
    
    if not room:
        return render_template('menu/error.html', 
                             message='رمز QR غير صحيح أو منتهي الصلاحية')
    
    # التحقق من وجود حجز نشط للغرفة
    current_time = datetime.now()
    active_booking = Booking.query.filter(
        Booking.room_id == room.id,
        Booking.start_time <= current_time,
        Booking.end_time >= current_time,
        Booking.status == 'active'
    ).first()
    
    if not active_booking:
        return render_template('menu/error.html',
                             message='لا يوجد حجز نشط لهذه الغرفة في الوقت الحالي')
    
    # إنشاء جلسة للعميل إذا لم تكن موجودة
    if 'customer_session' not in session:
        session['customer_session'] = str(uuid.uuid4())
        session['booking_id'] = active_booking.id
        session['room_id'] = room.id
    
    # جلب المنتجات والفئات
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    
    # تنظيم المنتجات حسب الفئات
    menu_data = []
    for category in categories:
        products = Product.query.filter_by(
            category_id=category.id,
            is_available=True
        ).all()
        
        if products:  # إضافة الفئة فقط إذا كان بها منتجات متاحة
            menu_data.append({
                'category': category,
                'products': products
            })
    
    # جلب السلة الحالية من الجلسة
    cart = session.get('cart', [])
    cart_total = sum(item['total'] for item in cart)
    
    return render_template('menu/room_menu.html',
                         room=room,
                         booking=active_booking,
                         menu_data=menu_data,
                         cart=cart,
                         cart_total=cart_total)

@menu_bp.route('/table/<int:table_number>')
def table_menu(table_number):
    """عرض المنيو للطاولات (مشابه للغرف)"""
    # منطق مشابه للغرف لكن للطاولات
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    
    menu_data = []
    for category in categories:
        products = Product.query.filter_by(
            category_id=category.id,
            is_available=True
        ).all()
        
        if products:
            menu_data.append({
                'category': category,
                'products': products
            })
    
    # إنشاء جلسة للطاولة
    if 'customer_session' not in session:
        session['customer_session'] = str(uuid.uuid4())
        session['table_number'] = table_number
    
    cart = session.get('cart', [])
    cart_total = sum(item['total'] for item in cart)
    
    return render_template('menu/table_menu.html',
                         table_number=table_number,
                         menu_data=menu_data,
                         cart=cart,
                         cart_total=cart_total)

@menu_bp.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    """إضافة منتج إلى السلة"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        notes = data.get('notes', '')
        
        product = Product.query.get(product_id)
        if not product or not product.is_available:
            return jsonify({'success': False, 'message': 'المنتج غير متوفر'})
        
        # التحقق من المخزون
        if product.stock_quantity < quantity:
            return jsonify({'success': False, 'message': 'مخزون غير كافي'})
        
        # إنشاء السلة إذا لم تكن موجودة
        if 'cart' not in session:
            session['cart'] = []
        
        cart = session['cart']
        
        # البحث عن المنتج في السلة
        existing_item = None
        for item in cart:
            if item['product_id'] == product_id and item['notes'] == notes:
                existing_item = item
                break
        
        if existing_item:
            # تحديث الكمية
            existing_item['quantity'] += quantity
            existing_item['total'] = existing_item['quantity'] * existing_item['price']
        else:
            # إضافة عنصر جديد
            cart_item = {
                'product_id': product_id,
                'name': product.name_ar,
                'price': float(product.price),
                'quantity': quantity,
                'total': float(product.price * quantity),
                'notes': notes
            }
            cart.append(cart_item)
        
        session['cart'] = cart
        session.modified = True
        
        # حساب إجمالي السلة
        cart_total = sum(item['total'] for item in cart)
        cart_count = sum(item['quantity'] for item in cart)
        
        return jsonify({
            'success': True,
            'message': 'تم إضافة المنتج إلى السلة',
            'cart_total': cart_total,
            'cart_count': cart_count
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@menu_bp.route('/remove-from-cart', methods=['POST'])
def remove_from_cart():
    """إزالة منتج من السلة"""
    try:
        data = request.get_json()
        cart_index = data.get('cart_index')
        
        if 'cart' not in session:
            return jsonify({'success': False, 'message': 'السلة فارغة'})
        
        cart = session['cart']
        
        if 0 <= cart_index < len(cart):
            cart.pop(cart_index)
            session['cart'] = cart
            session.modified = True
            
            cart_total = sum(item['total'] for item in cart)
            cart_count = sum(item['quantity'] for item in cart)
            
            return jsonify({
                'success': True,
                'message': 'تم إزالة المنتج من السلة',
                'cart_total': cart_total,
                'cart_count': cart_count
            })
        else:
            return jsonify({'success': False, 'message': 'عنصر غير صحيح'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@menu_bp.route('/update-cart', methods=['POST'])
def update_cart():
    """تحديث كمية في السلة"""
    try:
        data = request.get_json()
        cart_index = data.get('cart_index')
        new_quantity = int(data.get('quantity'))
        
        if new_quantity <= 0:
            return remove_from_cart()
        
        if 'cart' not in session:
            return jsonify({'success': False, 'message': 'السلة فارغة'})
        
        cart = session['cart']
        
        if 0 <= cart_index < len(cart):
            cart_item = cart[cart_index]
            
            # التحقق من المخزون
            product = Product.query.get(cart_item['product_id'])
            if product.stock_quantity < new_quantity:
                return jsonify({'success': False, 'message': 'مخزون غير كافي'})
            
            cart_item['quantity'] = new_quantity
            cart_item['total'] = cart_item['price'] * new_quantity
            
            session['cart'] = cart
            session.modified = True
            
            cart_total = sum(item['total'] for item in cart)
            cart_count = sum(item['quantity'] for item in cart)
            
            return jsonify({
                'success': True,
                'message': 'تم تحديث الكمية',
                'cart_total': cart_total,
                'cart_count': cart_count
            })
        else:
            return jsonify({'success': False, 'message': 'عنصر غير صحيح'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@menu_bp.route('/checkout')
def checkout():
    """صفحة إنهاء الطلب"""
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('menu.room_menu', room_qr=session.get('room_qr', '')))
    
    cart = session['cart']
    subtotal = sum(item['total'] for item in cart)
    tax = subtotal * 0.15
    total = subtotal + tax
    
    return render_template('menu/checkout.html',
                         cart=cart,
                         subtotal=subtotal,
                         tax=tax,
                         total=total)

@menu_bp.route('/place-order', methods=['POST'])
def place_order():
    """تأكيد الطلب وإرساله للمطبخ"""
    try:
        if 'cart' not in session or not session['cart']:
            return jsonify({'success': False, 'message': 'السلة فارغة'})
        
        cart = session['cart']
        booking_id = session.get('booking_id')
        customer_notes = request.json.get('notes', '')
        
        # إنشاء الطلب
        order = Order(
            booking_id=booking_id,
            notes=customer_notes
        )
        
        db.session.add(order)
        db.session.flush()
        
        total_amount = 0
        
        # إضافة عناصر الطلب
        for cart_item in cart:
            product = Product.query.get(cart_item['product_id'])
            
            # التحقق النهائي من المخزون
            if product.stock_quantity < cart_item['quantity']:
                db.session.rollback()
                return jsonify({
                    'success': False, 
                    'message': f'مخزون غير كافي للمنتج: {product.name_ar}'
                })
            
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=cart_item['quantity'],
                unit_price=product.price,
                notes=cart_item['notes']
            )
            
            db.session.add(order_item)
            total_amount += order_item.total_price
            
            # خصم من المخزون
            product.stock_quantity -= cart_item['quantity']
        
        # حساب الإجمالي
        order.subtotal = total_amount
        order.tax_amount = total_amount * 0.15
        order.total_amount = order.subtotal + order.tax_amount
        
        db.session.commit()
        
        # مسح السلة
        session.pop('cart', None)
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': 'تم تأكيد طلبكم وإرساله للمطبخ',
            'order_number': order.order_number,
            'estimated_time': 15  # وقت تقديري بالدقائق
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@menu_bp.route('/order-status/<string:order_number>')
def order_status(order_number):
    """تتبع حالة الطلب"""
    order = Order.query.filter_by(order_number=order_number).first()
    
    if not order:
        return render_template('menu/error.html',
                             message='رقم الطلب غير صحيح')
    
    # حساب الوقت المتوقع
    status_times = {
        'pending': 'قيد المراجعة',
        'preparing': '15-20 دقيقة',
        'ready': 'جاهز للاستلام',
        'delivered': 'تم التسليم'
    }
    
    estimated_time = status_times.get(order.status, 'غير محدد')
    
    return render_template('menu/order_status.html',
                         order=order,
                         estimated_time=estimated_time)

@menu_bp.route('/api/cart-count')
def cart_count():
    """API لعدد عناصر السلة"""
    cart = session.get('cart', [])
    count = sum(item['quantity'] for item in cart)
    total = sum(item['total'] for item in cart)
    
    return jsonify({
        'count': count,
        'total': total
    }) 