from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User, Role

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.main'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if user.is_active:
                login_user(user, remember=remember)
                flash('تم تسجيل الدخول بنجاح!', 'success')
                
                # Redirect to appropriate dashboard based on role
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                else:
                    return redirect(url_for('dashboard.main'))
            else:
                flash('حسابك معطل. يرجى التواصل مع الإدارة.', 'error')
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', user=current_user)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not check_password_hash(current_user.password_hash, current_password):
            flash('كلمة المرور الحالية غير صحيحة.', 'error')
        elif new_password != confirm_password:
            flash('كلمة المرور الجديدة وتأكيدها غير متطابقتين.', 'error')
        elif len(new_password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل.', 'error')
        else:
            from werkzeug.security import generate_password_hash
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('تم تغيير كلمة المرور بنجاح!', 'success')
            return redirect(url_for('auth.profile'))
    
    return render_template('auth/change_password.html') 