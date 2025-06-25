from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import db, Room, Booking, User
import uuid

booking_bp = Blueprint('booking', __name__)

@booking_bp.route('/')
@login_required
def index():
    """عرض جميع الغرف والحجوزات"""
    rooms = Room.query.filter_by(is_available=True).all()
    
    # الحجوزات النشطة اليوم
    today = datetime.now().date()
    active_bookings = Booking.query.filter(
        db.func.date(Booking.start_time) == today,
        Booking.status == 'active'
    ).all()
    
    return render_template('booking/index.html', 
                         rooms=rooms, 
                         active_bookings=active_bookings)

@booking_bp.route('/room/<int:room_id>')
@login_required
def room_details(room_id):
    """تفاصيل غرفة معينة وحجوزاتها"""
    room = Room.query.get_or_404(room_id)
    
    # حجوزات الغرفة لهذا الأسبوع
    today = datetime.now().date()
    week_end = today + timedelta(days=7)
    
    bookings = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.start_time >= today,
        Booking.start_time <= week_end
    ).order_by(Booking.start_time).all()
    
    return render_template('booking/room_details.html', 
                         room=room, 
                         bookings=bookings)

@booking_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_booking():
    """إنشاء حجز جديد"""
    if request.method == 'POST':
        room_id = request.form.get('room_id')
        customer_name = request.form.get('customer_name')
        customer_phone = request.form.get('customer_phone')
        start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
        duration_hours = float(request.form.get('duration_hours'))
        
        end_time = start_time + timedelta(hours=duration_hours)
        
        # التحقق من توفر الغرفة
        conflicting_booking = Booking.query.filter(
            Booking.room_id == room_id,
            Booking.status == 'active',
            db.or_(
                db.and_(Booking.start_time <= start_time, Booking.end_time > start_time),
                db.and_(Booking.start_time < end_time, Booking.end_time >= end_time),
                db.and_(Booking.start_time >= start_time, Booking.end_time <= end_time)
            )
        ).first()
        
        if conflicting_booking:
            flash('الغرفة محجوزة في هذا الوقت. يرجى اختيار وقت آخر.', 'error')
        else:
            room = Room.query.get(room_id)
            total_cost = duration_hours * room.hourly_rate
            
            booking = Booking(
                room_id=room_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                start_time=start_time,
                end_time=end_time,
                total_hours=duration_hours,
                total_cost=total_cost
            )
            
            db.session.add(booking)
            db.session.commit()
            
            flash('تم إنشاء الحجز بنجاح!', 'success')
            return redirect(url_for('booking.booking_details', booking_id=booking.id))
    
    rooms = Room.query.filter_by(is_available=True).all()
    return render_template('booking/new_booking.html', rooms=rooms)

@booking_bp.route('/booking/<int:booking_id>')
@login_required
def booking_details(booking_id):
    """تفاصيل حجز معين"""
    booking = Booking.query.get_or_404(booking_id)
    
    # QR Code للمنيو
    qr_code = booking.room.generate_menu_qr()
    
    return render_template('booking/booking_details.html', 
                         booking=booking, 
                         qr_code=qr_code)

@booking_bp.route('/booking/<int:booking_id>/extend', methods=['POST'])
@login_required
def extend_booking(booking_id):
    """تمديد حجز"""
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.status != 'active':
        return jsonify({'success': False, 'message': 'لا يمكن تمديد هذا الحجز'})
    
    additional_hours = float(request.json.get('hours', 1))
    new_end_time = booking.end_time + timedelta(hours=additional_hours)
    
    # التحقق من عدم وجود تعارض مع حجوزات أخرى
    conflicting_booking = Booking.query.filter(
        Booking.room_id == booking.room_id,
        Booking.id != booking.id,
        Booking.status == 'active',
        Booking.start_time < new_end_time,
        Booking.start_time > booking.end_time
    ).first()
    
    if conflicting_booking:
        return jsonify({
            'success': False, 
            'message': 'لا يمكن التمديد، الغرفة محجوزة في الفترة المطلوبة'
        })
    
    # تحديث الحجز
    additional_cost = additional_hours * booking.room.hourly_rate
    booking.end_time = new_end_time
    booking.total_hours += additional_hours
    booking.total_cost += additional_cost
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'تم تمديد الحجز بنجاح',
        'new_end_time': new_end_time.strftime('%Y-%m-%d %H:%M'),
        'additional_cost': additional_cost,
        'new_total_cost': booking.total_cost
    })

@booking_bp.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """إلغاء حجز"""
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.status != 'active':
        return jsonify({'success': False, 'message': 'لا يمكن إلغاء هذا الحجز'})
    
    booking.status = 'cancelled'
    db.session.commit()
    
    flash('تم إلغاء الحجز بنجاح.', 'info')
    return jsonify({'success': True, 'message': 'تم إلغاء الحجز بنجاح'})

@booking_bp.route('/booking/<int:booking_id>/complete', methods=['POST'])
@login_required
def complete_booking(booking_id):
    """إنهاء حجز"""
    booking = Booking.query.get_or_404(booking_id)
    
    booking.status = 'completed'
    booking.end_time = datetime.now()
    
    # إعادة حساب التكلفة الفعلية
    actual_hours = (booking.end_time - booking.start_time).total_seconds() / 3600
    booking.total_hours = actual_hours
    booking.total_cost = actual_hours * booking.room.hourly_rate
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'تم إنهاء الحجز بنجاح',
        'actual_cost': booking.total_cost
    })

@booking_bp.route('/api/room-availability')
@login_required
def room_availability():
    """API للتحقق من توفر الغرف"""
    room_id = request.args.get('room_id')
    start_time = datetime.strptime(request.args.get('start_time'), '%Y-%m-%dT%H:%M')
    end_time = datetime.strptime(request.args.get('end_time'), '%Y-%m-%dT%H:%M')
    
    conflicting_booking = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.status == 'active',
        db.or_(
            db.and_(Booking.start_time <= start_time, Booking.end_time > start_time),
            db.and_(Booking.start_time < end_time, Booking.end_time >= end_time),
            db.and_(Booking.start_time >= start_time, Booking.end_time <= end_time)
        )
    ).first()
    
    return jsonify({
        'available': conflicting_booking is None,
        'conflict': conflicting_booking.id if conflicting_booking else None
    }) 