from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, date

# Import configuration and models
from config import Config
from models import db, User, Role, create_default_data

# Import routes
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.booking import booking_bp
from routes.pos import pos_bp
from routes.menu import menu_bp
from routes.attendance import attendance_bp
from routes.inventory import inventory_bp
from routes.reports import reports_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(booking_bp, url_prefix='/booking')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(menu_bp, url_prefix='/menu')
    app.register_blueprint(attendance_bp, url_prefix='/attendance')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    
    # Create tables and default data
    with app.app_context():
        db.create_all()
        create_default_data()
        
        # Create default admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin_role = Role.query.filter_by(name='admin').first()
            admin_user = User(
                username='admin',
                email='admin@fikracafe.com',
                password_hash=generate_password_hash('admin123'),
                first_name='مدير',
                last_name='النظام',
                role_id=admin_role.id,
                employee_id='EMP001'
            )
            db.session.add(admin_user)
            db.session.commit()
    
    # Home route
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.main'))
        return render_template('landing.html')
    
    # Permission helper function
    def has_permission(permission):
        """تحقق من وجود صلاحية معينة للمستخدم الحالي"""
        if not current_user.is_authenticated:
            return False
        
        user_permissions = current_user.user_role.permissions or []
        return 'all' in user_permissions or permission in user_permissions

    # Context processors
    @app.context_processor
    def inject_globals():
        return {
            'current_year': datetime.now().year,
            'cafe_name': app.config['CAFE_NAME'],
            'current_date': date.today(),
            'has_permission': has_permission
        }
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # Template filters
    @app.template_filter('datetime')
    def datetime_filter(value, format='%Y-%m-%d %H:%M'):
        if value is None:
            return ""
        return value.strftime(format)
    
    @app.template_filter('currency')
    def currency_filter(value):
        if value is None:
            return "0.00 ريال"
        return f"{value:.2f} ريال"
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000) 