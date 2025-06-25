from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from models import db, User, Attendance, Role
import re

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/')
@login_required
def index():
    """عرض سجلات الحضور"""
    today = date.today()
    
    # فلترة بالتاريخ إذا تم تمرير معاملات
    filter_date = request.args.get('date')
    if filter_date:
        try:
            filter_date = datetime.strptime(filter_date, '%Y-%m-%d').date()
        except:
            filter_date = today
    else:
        filter_date = today
    
    # جلب سجلات الحضور لليوم المحدد
    attendance_records = db.session.query(Attendance, User).join(
        User, Attendance.employee_id == User.id
    ).filter(
        Attendance.date == filter_date
    ).order_by(User.first_name, User.last_name).all()
    
    # جلب جميع الموظفين النشطين
    active_employees = User.query.filter_by(is_active=True).all()
    
    # إنشاء قائمة شاملة بجميع الموظفين مع حالة الحضور
    employee_attendance = []
    for employee in active_employees:
        # البحث عن سجل حضور للموظف في هذا التاريخ
        attendance_record = None
        for record, user in attendance_records:
            if user.id == employee.id:
                attendance_record = record
                break
        
        if not attendance_record:
            # إنشاء سجل غياب افتراضي
            attendance_record = Attendance(
                employee_id=employee.id,
                date=filter_date,
                status='absent'
            )
        
        employee_attendance.append({
            'employee': employee,
            'attendance': attendance_record
        })
    
    return render_template('attendance/index.html', 
                         employee_attendance=employee_attendance,
                         filter_date=filter_date)

@attendance_bp.route('/qr-generator')
@login_required
def qr_generator():
    """صفحة توليد QR للموظفين"""
    employees = User.query.filter_by(is_active=True).all()
    
    # توليد QR جديد لكل موظف
    employee_qrs = []
    for employee in employees:
        qr_code = employee.generate_attendance_qr()
        employee_qrs.append({
            'employee': employee,
            'qr_code': qr_code,
            'expiry': employee.qr_expiry
        })
        
    db.session.commit()
    
    return render_template('attendance/qr_generator.html', 
                         employee_qrs=employee_qrs)

@attendance_bp.route('/scan')
def scan_qr():
    """صفحة مسح QR للحضور والانصراف"""
    return render_template('attendance/scan_qr.html')

@attendance_bp.route('/process-qr', methods=['POST'])
def process_qr():
    """معالجة QR المسحوب"""
    qr_data = request.json.get('qr_data')
    
    if not qr_data:
        return jsonify({'success': False, 'message': 'بيانات QR غير صحيحة'})
    
    # تحليل بيانات QR
    try:
        parts = qr_data.split(':')
        if len(parts) != 3 or parts[0] != 'attendance':
            return jsonify({'success': False, 'message': 'رمز QR غير صالح'})
        
        user_id = int(parts[1])
        token = parts[2]
        
    except (ValueError, IndexError):
        return jsonify({'success': False, 'message': 'تنسيق رمز QR غير صحيح'})
    
    # البحث عن المستخدم والتحقق من صحة الرمز
    user = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({'success': False, 'message': 'مستخدم غير صالح'})
    
    if user.current_qr_token != token or not user.is_qr_valid():
        return jsonify({'success': False, 'message': 'رمز QR منتهي الصلاحية أو غير صحيح'})
    
    today = date.today()
    current_time = datetime.now()
    
    # البحث عن سجل حضور لهذا اليوم
    attendance_record = Attendance.query.filter_by(
        employee_id=user_id,
        date=today
    ).first()
    
    if not attendance_record:
        # تسجيل دخول جديد
        attendance_record = Attendance(
            employee_id=user_id,
            date=today,
            check_in=current_time,
            status='present'
        )
        db.session.add(attendance_record)
        action = 'تسجيل دخول'
        
    elif attendance_record.check_in and not attendance_record.check_out:
        # تسجيل خروج
        attendance_record.check_out = current_time
        attendance_record.calculate_hours()
        action = 'تسجيل خروج'
        
    else:
        return jsonify({'success': False, 'message': 'تم تسجيل الدخول والخروج مسبقاً لهذا اليوم'})
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'تم {action} بنجاح',
        'employee_name': f"{user.first_name} {user.last_name}",
        'time': current_time.strftime('%H:%M:%S'),
        'action': action
    })

@attendance_bp.route('/manual-entry', methods=['GET', 'POST'])
@login_required
def manual_entry():
    """إدخال حضور يدوي"""
    # التحقق من الصلاحيات
    if not (current_user.user_role.name in ['admin', 'hr'] or 
            'record_attendance' in current_user.user_role.permissions):
        flash('ليس لديك صلاحية لتسجيل الحضور يدوياً.', 'error')
        return redirect(url_for('attendance.index'))
    
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        attendance_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        check_in_time = request.form.get('check_in')
        check_out_time = request.form.get('check_out')
        status = request.form.get('status')
        notes = request.form.get('notes')
        
        # التحقق من وجود سجل مسبق
        existing_record = Attendance.query.filter_by(
            employee_id=employee_id,
            date=attendance_date
        ).first()
        
        if existing_record:
            # تحديث السجل الموجود
            attendance_record = existing_record
        else:
            # إنشاء سجل جديد
            attendance_record = Attendance(
                employee_id=employee_id,
                date=attendance_date
            )
            db.session.add(attendance_record)
        
        # تحديث البيانات
        if check_in_time:
            attendance_record.check_in = datetime.combine(attendance_date, 
                                                        datetime.strptime(check_in_time, '%H:%M').time())
        
        if check_out_time:
            attendance_record.check_out = datetime.combine(attendance_date, 
                                                         datetime.strptime(check_out_time, '%H:%M').time())
        
        attendance_record.status = status
        attendance_record.notes = notes
        
        # حساب ساعات العمل
        attendance_record.calculate_hours()
        
        db.session.commit()
        flash('تم تسجيل الحضور بنجاح!', 'success')
        return redirect(url_for('attendance.index'))
    
    employees = User.query.filter_by(is_active=True).all()
    return render_template('attendance/manual_entry.html', employees=employees)

@attendance_bp.route('/reports')
@login_required
def reports():
    """تقارير الحضور"""
    # التحقق من الصلاحيات
    if not (current_user.user_role.name in ['admin', 'hr'] or 
            'view_attendance' in current_user.user_role.permissions):
        flash('ليس لديك صلاحية لعرض تقارير الحضور.', 'error')
        return redirect(url_for('attendance.index'))
    
    # فلاتر التقرير
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_id = request.args.get('employee_id')
    
    # تعيين تواريخ افتراضية (آخر 30 يوم)
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')
    
    # بناء الاستعلام
    query = db.session.query(Attendance, User).join(User, Attendance.employee_id == User.id)
    
    query = query.filter(
        Attendance.date >= datetime.strptime(start_date, '%Y-%m-%d').date(),
        Attendance.date <= datetime.strptime(end_date, '%Y-%m-%d').date()
    )
    
    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)
    
    attendance_records = query.order_by(Attendance.date.desc(), User.first_name).all()
    
    # إحصائيات إجمالية
    total_days = (datetime.strptime(end_date, '%Y-%m-%d').date() - 
                  datetime.strptime(start_date, '%Y-%m-%d').date()).days + 1
    
    stats = {}
    for record, user in attendance_records:
        emp_id = user.id
        if emp_id not in stats:
            stats[emp_id] = {
                'employee': user,
                'present_days': 0,
                'absent_days': 0,
                'late_days': 0,
                'total_hours': 0
            }
        
        if record.status == 'present':
            stats[emp_id]['present_days'] += 1
            if record.total_hours:
                stats[emp_id]['total_hours'] += record.total_hours
        elif record.status == 'absent':
            stats[emp_id]['absent_days'] += 1
        elif record.status == 'late':
            stats[emp_id]['late_days'] += 1
            if record.total_hours:
                stats[emp_id]['total_hours'] += record.total_hours
    
    employees = User.query.filter_by(is_active=True).all()
    
    return render_template('attendance/reports.html',
                         attendance_records=attendance_records,
                         stats=stats,
                         employees=employees,
                         start_date=start_date,
                         end_date=end_date,
                         employee_id=employee_id) 