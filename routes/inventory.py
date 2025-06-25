from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date
from models import db, Product, Category, Inventory, User
from sqlalchemy import func

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/')
@login_required
def index():
    """عرض جميع المنتجات والمخزون"""
    products = Product.query.all()
    
    # المنتجات منخفضة المخزون
    low_stock = Product.query.filter(
        Product.stock_quantity <= Product.min_stock_level
    ).all()
    
    # إحصائيات سريعة
    total_products = Product.query.count()
    out_of_stock = Product.query.filter_by(stock_quantity=0).count()
    low_stock_count = len(low_stock)
    
    return render_template('inventory/index.html',
                         products=products,
                         low_stock=low_stock,
                         total_products=total_products,
                         out_of_stock=out_of_stock,
                         low_stock_count=low_stock_count)

@inventory_bp.route('/products')
@login_required
def products():
    """إدارة المنتجات"""
    categories = Category.query.all()
    products = Product.query.order_by(Product.name_ar).all()
    
    return render_template('inventory/products.html',
                         categories=categories,
                         products=products)

@inventory_bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    """إضافة منتج جديد"""
    if request.method == 'POST':
        try:
            product = Product(
                name=request.form.get('name'),
                name_ar=request.form.get('name_ar'),
                description=request.form.get('description'),
                price=float(request.form.get('price')),
                cost_price=float(request.form.get('cost_price', 0)),
                category_id=int(request.form.get('category_id')),
                stock_quantity=int(request.form.get('stock_quantity', 0)),
                min_stock_level=int(request.form.get('min_stock_level', 5)),
                unit=request.form.get('unit', 'piece'),
                preparation_time=int(request.form.get('preparation_time', 5)),
                is_available=bool(request.form.get('is_available'))
            )
            
            db.session.add(product)
            db.session.commit()
            
            # تسجيل حركة مخزون أولية إذا كانت الكمية أكبر من صفر
            if product.stock_quantity > 0:
                inventory_transaction = Inventory(
                    product_id=product.id,
                    transaction_type='purchase',
                    quantity=product.stock_quantity,
                    unit_cost=product.cost_price,
                    total_cost=product.cost_price * product.stock_quantity,
                    notes='مخزون أولي',
                    created_by=current_user.id
                )
                db.session.add(inventory_transaction)
                db.session.commit()
            
            flash('تم إضافة المنتج بنجاح!', 'success')
            return redirect(url_for('inventory.products'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في إضافة المنتج: {str(e)}', 'error')
    
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('inventory/new_product.html', categories=categories)

@inventory_bp.route('/product/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    """تعديل منتج"""
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        try:
            product.name = request.form.get('name')
            product.name_ar = request.form.get('name_ar')
            product.description = request.form.get('description')
            product.price = float(request.form.get('price'))
            product.cost_price = float(request.form.get('cost_price', 0))
            product.category_id = int(request.form.get('category_id'))
            product.min_stock_level = int(request.form.get('min_stock_level', 5))
            product.unit = request.form.get('unit', 'piece')
            product.preparation_time = int(request.form.get('preparation_time', 5))
            product.is_available = bool(request.form.get('is_available'))
            
            db.session.commit()
            flash('تم تحديث المنتج بنجاح!', 'success')
            return redirect(url_for('inventory.products'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تحديث المنتج: {str(e)}', 'error')
    
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('inventory/edit_product.html', 
                         product=product, 
                         categories=categories)

@inventory_bp.route('/product/<int:product_id>/stock')
@login_required
def product_stock_history(product_id):
    """تاريخ حركات المخزون للمنتج"""
    product = Product.query.get_or_404(product_id)
    
    transactions = db.session.query(Inventory, User).outerjoin(
        User, Inventory.created_by == User.id
    ).filter(
        Inventory.product_id == product_id
    ).order_by(Inventory.created_at.desc()).all()
    
    return render_template('inventory/product_stock_history.html',
                         product=product,
                         transactions=transactions)

@inventory_bp.route('/stock-adjustment', methods=['GET', 'POST'])
@login_required
def stock_adjustment():
    """تعديل المخزون"""
    if request.method == 'POST':
        try:
            product_id = int(request.form.get('product_id'))
            adjustment_type = request.form.get('adjustment_type')
            quantity = int(request.form.get('quantity'))
            notes = request.form.get('notes', '')
            
            product = Product.query.get(product_id)
            if not product:
                flash('المنتج غير موجود', 'error')
                return redirect(url_for('inventory.stock_adjustment'))
            
            # تحديد نوع المعاملة
            if adjustment_type == 'add':
                product.stock_quantity += quantity
                transaction_type = 'adjustment'
                transaction_quantity = quantity
            elif adjustment_type == 'subtract':
                if product.stock_quantity >= quantity:
                    product.stock_quantity -= quantity
                    transaction_type = 'adjustment'
                    transaction_quantity = -quantity
                else:
                    flash('الكمية المطلوب خصمها أكبر من المخزون المتاح', 'error')
                    return redirect(url_for('inventory.stock_adjustment'))
            
            # تسجيل المعاملة
            inventory_transaction = Inventory(
                product_id=product_id,
                transaction_type=transaction_type,
                quantity=transaction_quantity,
                notes=notes,
                created_by=current_user.id
            )
            
            db.session.add(inventory_transaction)
            db.session.commit()
            
            flash('تم تعديل المخزون بنجاح!', 'success')
            return redirect(url_for('inventory.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تعديل المخزون: {str(e)}', 'error')
    
    products = Product.query.order_by(Product.name_ar).all()
    return render_template('inventory/stock_adjustment.html', products=products)

@inventory_bp.route('/purchase', methods=['GET', 'POST'])
@login_required
def new_purchase():
    """تسجيل مشتريات جديدة"""
    if request.method == 'POST':
        try:
            # معلومات الفاتورة
            supplier_name = request.form.get('supplier_name')
            invoice_number = request.form.get('invoice_number')
            purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d')
            notes = request.form.get('notes', '')
            
            # عناصر المشتريات
            products_data = request.form.getlist('products')
            quantities = request.form.getlist('quantities')
            unit_costs = request.form.getlist('unit_costs')
            
            total_cost = 0
            
            for i, product_id in enumerate(products_data):
                if product_id and quantities[i] and unit_costs[i]:
                    product = Product.query.get(int(product_id))
                    quantity = int(quantities[i])
                    unit_cost = float(unit_costs[i])
                    item_total = quantity * unit_cost
                    
                    # تحديث المخزون
                    product.stock_quantity += quantity
                    product.cost_price = unit_cost  # تحديث تكلفة الوحدة
                    
                    # تسجيل المعاملة
                    inventory_transaction = Inventory(
                        product_id=product.id,
                        transaction_type='purchase',
                        quantity=quantity,
                        unit_cost=unit_cost,
                        total_cost=item_total,
                        notes=f'فاتورة: {invoice_number} - مورد: {supplier_name}',
                        created_by=current_user.id
                    )
                    
                    db.session.add(inventory_transaction)
                    total_cost += item_total
            
            db.session.commit()
            flash(f'تم تسجيل المشتريات بنجاح! إجمالي التكلفة: {total_cost:.2f} ريال', 'success')
            return redirect(url_for('inventory.purchase_history'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تسجيل المشتريات: {str(e)}', 'error')
    
    products = Product.query.order_by(Product.name_ar).all()
    return render_template('inventory/new_purchase.html', products=products)

@inventory_bp.route('/purchase-history')
@login_required
def purchase_history():
    """تاريخ المشتريات"""
    purchases = db.session.query(Inventory, Product, User).join(
        Product, Inventory.product_id == Product.id
    ).outerjoin(
        User, Inventory.created_by == User.id
    ).filter(
        Inventory.transaction_type == 'purchase'
    ).order_by(Inventory.created_at.desc()).all()
    
    return render_template('inventory/purchase_history.html', purchases=purchases)

@inventory_bp.route('/categories')
@login_required
def categories():
    """إدارة فئات المنتجات"""
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('inventory/categories.html', categories=categories)

@inventory_bp.route('/category/new', methods=['POST'])
@login_required
def new_category():
    """إضافة فئة جديدة"""
    try:
        category = Category(
            name=request.form.get('name'),
            name_ar=request.form.get('name_ar'),
            description=request.form.get('description'),
            sort_order=int(request.form.get('sort_order', 0)),
            is_active=bool(request.form.get('is_active', True))
        )
        
        db.session.add(category)
        db.session.commit()
        
        flash('تم إضافة الفئة بنجاح!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في إضافة الفئة: {str(e)}', 'error')
    
    return redirect(url_for('inventory.categories'))

@inventory_bp.route('/reports')
@login_required
def reports():
    """تقارير المخزون"""
    # تقرير المنتجات منخفضة المخزون
    low_stock_products = Product.query.filter(
        Product.stock_quantity <= Product.min_stock_level
    ).all()
    
    # تقرير المنتجات نافدة المخزون
    out_of_stock_products = Product.query.filter_by(stock_quantity=0).all()
    
    # أحدث المعاملات
    recent_transactions = db.session.query(Inventory, Product, User).join(
        Product, Inventory.product_id == Product.id
    ).outerjoin(
        User, Inventory.created_by == User.id
    ).order_by(Inventory.created_at.desc()).limit(20).all()
    
    # قيمة المخزون الإجمالية
    total_inventory_value = db.session.query(
        func.sum(Product.stock_quantity * Product.cost_price)
    ).scalar() or 0
    
    return render_template('inventory/reports.html',
                         low_stock_products=low_stock_products,
                         out_of_stock_products=out_of_stock_products,
                         recent_transactions=recent_transactions,
                         total_inventory_value=total_inventory_value)

@inventory_bp.route('/api/product-info/<int:product_id>')
@login_required
def product_info(product_id):
    """API للحصول على معلومات المنتج"""
    product = Product.query.get_or_404(product_id)
    
    return jsonify({
        'id': product.id,
        'name': product.name_ar,
        'current_stock': product.stock_quantity,
        'min_stock_level': product.min_stock_level,
        'unit': product.unit,
        'cost_price': float(product.cost_price or 0),
        'price': float(product.price)
    }) 