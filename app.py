"""
Warranty Adjudication Management System
Aerospace Part 145 MRO Company
"""
import os
import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

# ─────────────────────────────────────────────────────────────────────────────
# APP CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY',
    'aerospace-wam-secret-change-in-prod-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///warranty.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

# Créer les tables automatiquement au démarrage (init_db_cmd défini plus bas)
def _init_db():
    """Create tables and seed reference data (called at startup and via CLI)."""
    db.create_all()

    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@mro.aero',
                     first_name='Admin', last_name='User', role='admin')
        admin.set_password('Admin123!')
        db.session.add(admin)

    for uname, email, fn, ln in [
        ('j.smith',   'j.smith@mro.aero',   'James',  'Smith'),
        ('m.wilson',  'm.wilson@mro.aero',  'Marie',  'Wilson'),
        ('s.martin',  's.martin@mro.aero',  'Sophie', 'Martin'),
        ('r.johnson', 'r.johnson@mro.aero', 'Robert', 'Johnson'),
        ('p.dubois',  'p.dubois@mro.aero',  'Pierre', 'Dubois'),
    ]:
        if not User.query.filter_by(username=uname).first():
            u = User(username=uname, email=email, first_name=fn,
                     last_name=ln, role='engineer')
            u.set_password('Engineer1!')
            db.session.add(u)

    for code, name, email, country in [
        ('AIR_FR',    'Air France',       'warranty@airfrance.fr',        'France'),
        ('LUFTH',     'Lufthansa Technik','warranty@lufthansa-technik.de', 'Germany'),
        ('EMIRATES',  'Emirates',         'mro@emirates.com',              'UAE'),
        ('BRIT_AW',   'British Airways',  'techops@ba.com',                'UK'),
        ('RYANAIR',   'Ryanair',          'mro@ryanair.com',               'Ireland'),
        ('EASYJET',   'easyJet',          'engineering@easyjet.com',       'UK'),
    ]:
        if not Customer.query.filter_by(code=code).first():
            db.session.add(Customer(code=code, name=name,
                                    contact_email=email, country=country))

    db.session.commit()

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
class WarrantyStatus:
    OPEN         = 'open'
    WORKSHOP     = 'workshop'
    ENGINEERING  = 'engineering'
    CLOSED       = 'closed'
    CHOICES = [
        (OPEN,        'Open'),
        (WORKSHOP,    'Under Workshop Investigation'),
        (ENGINEERING, 'Under Engineering Review'),
        (CLOSED,      'Closed'),
    ]
    LABELS = dict(CHOICES)
    COLORS = {
        OPEN:        'primary',
        WORKSHOP:    'warning',
        ENGINEERING: 'purple',
        CLOSED:      'secondary',
    }
    HEX = {
        OPEN:        '#0d6efd',
        WORKSHOP:    '#fd7e14',
        ENGINEERING: '#6f42c1',
        CLOSED:      '#6c757d',
    }


class ClosureDecision:
    ACCEPTED           = 'accepted'
    PARTIALLY_ACCEPTED = 'partially_accepted'
    REJECTED           = 'rejected'
    CHOICES = [
        (ACCEPTED,           'Accepted'),
        (PARTIALLY_ACCEPTED, 'Partially Accepted'),
        (REJECTED,           'Rejected'),
    ]
    LABELS = dict(CHOICES)
    COLORS = {
        ACCEPTED:           'success',
        PARTIALLY_ACCEPTED: 'warning',
        REJECTED:           'danger',
    }
    HEX = {
        ACCEPTED:           '#198754',
        PARTIALLY_ACCEPTED: '#ffc107',
        REJECTED:           '#dc3545',
    }


class ActivityType:
    CREATED           = 'created'
    STATUS_CHANGED    = 'status_changed'
    COMMENT_ADDED     = 'comment_added'
    ENGINEER_ASSIGNED = 'engineer_assigned'
    ENGINEER_REMOVED  = 'engineer_removed'
    EDITED            = 'edited'
    CLOSED            = 'closed'
    REOPENED          = 'reopened'

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE MODELS
# ─────────────────────────────────────────────────────────────────────────────
warranty_engineers = db.Table(
    'warranty_engineers',
    db.Column('warranty_id', db.Integer, db.ForeignKey('warranty.id'),  primary_key=True),
    db.Column('user_id',     db.Integer, db.ForeignKey('user.id'),      primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow),
)


class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name    = db.Column(db.String(80),  nullable=False)
    last_name     = db.Column(db.String(80),  nullable=False)
    role          = db.Column(db.String(20),  default='engineer')   # admin | engineer | viewer
    is_active     = db.Column(db.Boolean,     default=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    warranties_created = db.relationship('Warranty', backref='created_by_user',
                                         foreign_keys='Warranty.created_by_id')
    activities         = db.relationship('WarrantyActivity', backref='user',
                                         lazy='dynamic')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        return f"{self.first_name[0]}{self.last_name[0]}".upper()

    def __repr__(self):
        return f'<User {self.username}>'


class Customer(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    code          = db.Column(db.String(20),  unique=True, nullable=False)
    contact_email = db.Column(db.String(120))
    country       = db.Column(db.String(100))
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    warranties = db.relationship('Warranty', backref='customer', lazy='dynamic')

    def __repr__(self):
        return f'<Customer {self.code}>'


class Warranty(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    warranty_number  = db.Column(db.String(20), unique=True, nullable=False)

    # ── Part information
    lru_part_number   = db.Column(db.String(50),  nullable=False)
    lru_serial_number = db.Column(db.String(50),  nullable=False)
    lru_description   = db.Column(db.String(200))

    # ── Customer
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)

    # ── MCO (Maintenance/Check Order) information
    current_mco = db.Column(db.String(50), nullable=False)   # where unit is under investigation
    former_mco  = db.Column(db.String(50))                   # where unit was previously repaired

    # ── Dates
    former_arc_date         = db.Column(db.Date)             # former Authorised Release Certificate
    defect_date             = db.Column(db.Date)
    adjudication_start_date = db.Column(db.Date, nullable=False)
    installation_date       = db.Column(db.Date)

    # ── Defect
    observed_defect      = db.Column(db.Text, nullable=False)
    reason_for_removal   = db.Column(db.Text)
    ata_chapter          = db.Column(db.String(20))

    # ── Time parameters (flight hours)
    tsi                              = db.Column(db.Float)    # Time Since Installation
    tso                              = db.Column(db.Float)    # Time Since Overhaul
    flight_cycles_since_installation = db.Column(db.Integer)

    # ── Warranty status
    status            = db.Column(db.String(30), nullable=False, default=WarrantyStatus.OPEN)
    closure_decision  = db.Column(db.String(30))
    closure_comments  = db.Column(db.Text)
    closed_at         = db.Column(db.DateTime)
    closed_by_id      = db.Column(db.Integer, db.ForeignKey('user.id'))

    # ── Meta
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # ── Relationships
    engineers  = db.relationship('User', secondary=warranty_engineers,
                                 backref=db.backref('assigned_warranties', lazy='dynamic'))
    activities = db.relationship('WarrantyActivity', backref='warranty',
                                 lazy='dynamic', order_by='WarrantyActivity.timestamp')

    # ── Helpers
    @staticmethod
    def generate_warranty_number():
        year = datetime.utcnow().year
        last = (Warranty.query
                .filter(Warranty.warranty_number.like(f'WAR-{year}-%'))
                .order_by(Warranty.id.desc())
                .first())
        seq = (int(last.warranty_number.split('-')[-1]) + 1) if last else 1
        return f'WAR-{year}-{seq:05d}'

    @property
    def status_label(self):
        return WarrantyStatus.LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        if self.status == WarrantyStatus.CLOSED and self.closure_decision:
            return ClosureDecision.COLORS.get(self.closure_decision, 'secondary')
        return WarrantyStatus.COLORS.get(self.status, 'secondary')

    @property
    def status_hex(self):
        if self.status == WarrantyStatus.CLOSED and self.closure_decision:
            return ClosureDecision.HEX.get(self.closure_decision, '#6c757d')
        return WarrantyStatus.HEX.get(self.status, '#6c757d')

    @property
    def effective_status_label(self):
        if self.status == WarrantyStatus.CLOSED and self.closure_decision:
            return f"Closed — {ClosureDecision.LABELS.get(self.closure_decision)}"
        return self.status_label

    @property
    def closure_decision_label(self):
        return ClosureDecision.LABELS.get(self.closure_decision) if self.closure_decision else None

    @property
    def previous_warranties(self):
        return (Warranty.query
                .filter(Warranty.lru_serial_number == self.lru_serial_number,
                        Warranty.id != self.id)
                .order_by(Warranty.created_at.desc())
                .all())

    @property
    def previous_warranty_count(self):
        return (Warranty.query
                .filter(Warranty.lru_serial_number == self.lru_serial_number,
                        Warranty.id != self.id)
                .count())

    def __repr__(self):
        return f'<Warranty {self.warranty_number}>'


class WarrantyActivity(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    warranty_id   = db.Column(db.Integer, db.ForeignKey('warranty.id'), nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey('user.id'),     nullable=False)
    activity_type = db.Column(db.String(30), nullable=False)
    comment       = db.Column(db.Text)
    old_value     = db.Column(db.String(200))
    new_value     = db.Column(db.String(200))
    timestamp     = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def activity_icon(self):
        return {
            ActivityType.CREATED:           'fa-plus-circle',
            ActivityType.STATUS_CHANGED:    'fa-exchange-alt',
            ActivityType.COMMENT_ADDED:     'fa-comment-dots',
            ActivityType.ENGINEER_ASSIGNED: 'fa-user-plus',
            ActivityType.ENGINEER_REMOVED:  'fa-user-minus',
            ActivityType.EDITED:            'fa-pen',
            ActivityType.CLOSED:            'fa-lock',
            ActivityType.REOPENED:          'fa-lock-open',
        }.get(self.activity_type, 'fa-circle')

    @property
    def activity_color(self):
        return {
            ActivityType.CREATED:           'success',
            ActivityType.STATUS_CHANGED:    'warning',
            ActivityType.COMMENT_ADDED:     'info',
            ActivityType.ENGINEER_ASSIGNED: 'primary',
            ActivityType.ENGINEER_REMOVED:  'secondary',
            ActivityType.EDITED:            'warning',
            ActivityType.CLOSED:            'danger',
            ActivityType.REOPENED:          'success',
        }.get(self.activity_type, 'secondary')

# ─────────────────────────────────────────────────────────────────────────────
# LOGIN MANAGER
# ─────────────────────────────────────────────────────────────────────────────
@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE GLOBALS / FILTERS
# ─────────────────────────────────────────────────────────────────────────────
app.jinja_env.globals.update(
    WarrantyStatus=WarrantyStatus,
    ClosureDecision=ClosureDecision,
    ActivityType=ActivityType,
    now=datetime.utcnow,
)

@app.template_filter('fdate')
def fdate(value, fmt='%d %b %Y'):
    if value is None:
        return '—'
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    return value

@app.template_filter('fdatetime')
def fdatetime(value, fmt='%d %b %Y  %H:%M UTC'):
    if value is None:
        return '—'
    return value.strftime(fmt)

@app.template_filter('hours')
def hours(value):
    if value is None:
        return '—'
    return f"{value:,.1f} h"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def log_activity(warranty, activity_type, comment=None, old_value=None, new_value=None):
    db.session.add(WarrantyActivity(
        warranty_id=warranty.id,
        user_id=current_user.id,
        activity_type=activity_type,
        comment=comment,
        old_value=str(old_value) if old_value else None,
        new_value=str(new_value) if new_value else None,
    ))

def parse_date(s):
    return datetime.strptime(s, '%Y-%m-%d').date() if s else None

# ─────────────────────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/')
@login_required
def dashboard():
    status      = request.args.get('status', '')
    engineer_id = request.args.get('engineer', '')
    part_number = request.args.get('pn', '')
    customer_id = request.args.get('customer', '')
    search      = request.args.get('search', '')
    sort        = request.args.get('sort', 'newest')

    query = Warranty.query

    if status:
        query = query.filter(Warranty.status == status)
    if engineer_id:
        query = query.filter(Warranty.engineers.any(User.id == int(engineer_id)))
    if part_number:
        query = query.filter(Warranty.lru_part_number.ilike(f'%{part_number}%'))
    if customer_id:
        query = query.filter(Warranty.customer_id == int(customer_id))
    if search:
        query = query.filter(db.or_(
            Warranty.warranty_number.ilike(f'%{search}%'),
            Warranty.lru_part_number.ilike(f'%{search}%'),
            Warranty.lru_serial_number.ilike(f'%{search}%'),
            Warranty.observed_defect.ilike(f'%{search}%'),
        ))

    if sort == 'oldest':
        query = query.order_by(Warranty.created_at.asc())
    elif sort == 'updated':
        query = query.order_by(Warranty.updated_at.desc())
    else:
        query = query.order_by(Warranty.created_at.desc())

    warranties = query.all()

    stats = {
        'total':       Warranty.query.count(),
        'open':        Warranty.query.filter_by(status=WarrantyStatus.OPEN).count(),
        'workshop':    Warranty.query.filter_by(status=WarrantyStatus.WORKSHOP).count(),
        'engineering': Warranty.query.filter_by(status=WarrantyStatus.ENGINEERING).count(),
        'closed':      Warranty.query.filter_by(status=WarrantyStatus.CLOSED).count(),
    }

    return render_template('dashboard.html',
        warranties=warranties,
        stats=stats,
        engineers=User.query.filter_by(is_active=True).order_by(User.last_name).all(),
        customers=Customer.query.filter_by(is_active=True).order_by(Customer.name).all(),
        filters={'status': status, 'engineer': engineer_id, 'pn': part_number,
                 'customer': customer_id, 'search': search, 'sort': sort},
    )

# ─────────────────────────────────────────────────────────────────────────────
# WARRANTY — NEW
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/warranty/new', methods=['GET', 'POST'])
@login_required
def warranty_new():
    customers = Customer.query.filter_by(is_active=True).order_by(Customer.name).all()
    engineers = User.query.filter_by(is_active=True).order_by(User.last_name).all()

    if request.method == 'POST':
        try:
            w = Warranty(
                warranty_number         = Warranty.generate_warranty_number(),
                lru_part_number         = request.form['lru_part_number'].strip().upper(),
                lru_serial_number       = request.form['lru_serial_number'].strip().upper(),
                lru_description         = request.form.get('lru_description', '').strip() or None,
                customer_id             = int(request.form['customer_id']),
                current_mco             = request.form['current_mco'].strip().upper(),
                former_mco              = request.form.get('former_mco', '').strip().upper() or None,
                former_arc_date         = parse_date(request.form.get('former_arc_date')),
                defect_date             = parse_date(request.form.get('defect_date')),
                adjudication_start_date = parse_date(request.form['adjudication_start_date']),
                installation_date       = parse_date(request.form.get('installation_date')),
                observed_defect         = request.form['observed_defect'].strip(),
                reason_for_removal      = request.form.get('reason_for_removal', '').strip() or None,
                ata_chapter             = request.form.get('ata_chapter', '').strip() or None,
                tsi                     = float(request.form['tsi']) if request.form.get('tsi') else None,
                tso                     = float(request.form['tso']) if request.form.get('tso') else None,
                flight_cycles_since_installation = int(request.form['flight_cycles']) if request.form.get('flight_cycles') else None,
                created_by_id           = current_user.id,
            )
            db.session.add(w)
            db.session.flush()

            eng_ids = request.form.getlist('engineer_ids')
            eng_names = []
            for eid in eng_ids:
                eng = User.query.get(int(eid))
                if eng:
                    w.engineers.append(eng)
                    eng_names.append(eng.full_name)

            log_activity(w, ActivityType.CREATED,
                comment=f'Warranty {w.warranty_number} created for LRU {w.lru_part_number} / S/N {w.lru_serial_number}.')
            if eng_names:
                log_activity(w, ActivityType.ENGINEER_ASSIGNED,
                    comment=f'Assigned engineers: {", ".join(eng_names)}')

            db.session.commit()
            flash(f'Warranty <strong>{w.warranty_number}</strong> created successfully.', 'success')
            return redirect(url_for('warranty_detail', warranty_id=w.id))

        except Exception as exc:
            db.session.rollback()
            flash(f'Error creating warranty: {exc}', 'danger')

    return render_template('warranty_new.html',
        customers=customers, engineers=engineers,
        today=date.today().isoformat())

# ─────────────────────────────────────────────────────────────────────────────
# WARRANTY — DETAIL
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/warranty/<int:warranty_id>')
@login_required
def warranty_detail(warranty_id):
    w = Warranty.query.get_or_404(warranty_id)
    activities = w.activities.order_by(WarrantyActivity.timestamp.asc()).all()
    return render_template('warranty_detail.html',
        w=w,
        activities=activities,
        all_engineers=User.query.filter_by(is_active=True).order_by(User.last_name).all(),
        previous_warranties=w.previous_warranties,
    )

# ─────────────────────────────────────────────────────────────────────────────
# WARRANTY — EDIT
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/warranty/<int:warranty_id>/edit', methods=['GET', 'POST'])
@login_required
def warranty_edit(warranty_id):
    w = Warranty.query.get_or_404(warranty_id)
    customers = Customer.query.filter_by(is_active=True).order_by(Customer.name).all()
    engineers = User.query.filter_by(is_active=True).order_by(User.last_name).all()

    if request.method == 'POST':
        try:
            changes = []

            def track(field, label, transform=lambda x: x):
                raw = request.form.get(field, '').strip()
                new_val = transform(raw) if raw else None
                old_val = getattr(w, field)
                if new_val != old_val:
                    changes.append(f'{label}: «{old_val}» → «{new_val}»')
                    setattr(w, field, new_val)

            track('lru_part_number',    'LRU P/N',          str.upper)
            track('lru_serial_number',  'LRU S/N',          str.upper)
            track('lru_description',    'Description')
            track('current_mco',        'Current MCO',      str.upper)
            track('former_mco',         'Former MCO',       str.upper)
            track('observed_defect',    'Observed Defect')
            track('reason_for_removal', 'Reason for Removal')
            track('ata_chapter',        'ATA Chapter',      str.upper)

            for f, lbl in [('tsi', 'TSI'), ('tso', 'TSO')]:
                raw = request.form.get(f, '')
                new_v = float(raw) if raw else None
                old_v = getattr(w, f)
                if new_v != old_v:
                    changes.append(f'{lbl}: {old_v} → {new_v}')
                    setattr(w, f, new_v)

            fc_raw = request.form.get('flight_cycles', '')
            new_fc = int(fc_raw) if fc_raw else None
            if new_fc != w.flight_cycles_since_installation:
                changes.append(f'Flight Cycles: {w.flight_cycles_since_installation} → {new_fc}')
                w.flight_cycles_since_installation = new_fc

            new_cust = int(request.form['customer_id'])
            if new_cust != w.customer_id:
                old_c = Customer.query.get(w.customer_id)
                new_c = Customer.query.get(new_cust)
                changes.append(f'Customer: {old_c.name} → {new_c.name}')
                w.customer_id = new_cust

            for df, lbl in [('former_arc_date', 'Former ARC Date'), ('defect_date', 'Defect Date'),
                             ('adjudication_start_date', 'Adjudication Start'),
                             ('installation_date', 'Installation Date')]:
                new_d = parse_date(request.form.get(df, ''))
                old_d = getattr(w, df)
                if new_d != old_d:
                    changes.append(f'{lbl}: {old_d} → {new_d}')
                    setattr(w, df, new_d)

            w.updated_at = datetime.utcnow()

            if changes:
                log_activity(w, ActivityType.EDITED,
                    comment='Fields updated:\n• ' + '\n• '.join(changes))

            db.session.commit()
            flash('Warranty updated successfully.', 'success')
            return redirect(url_for('warranty_detail', warranty_id=w.id))

        except Exception as exc:
            db.session.rollback()
            flash(f'Error updating warranty: {exc}', 'danger')

    return render_template('warranty_edit.html',
        w=w, customers=customers, engineers=engineers)

# ─────────────────────────────────────────────────────────────────────────────
# WARRANTY — STATUS UPDATE
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/warranty/<int:warranty_id>/update-status', methods=['POST'])
@login_required
def update_status(warranty_id):
    w = Warranty.query.get_or_404(warranty_id)
    new_status = request.form.get('status', '')
    comment    = request.form.get('comment', '').strip()

    if new_status not in dict(WarrantyStatus.CHOICES):
        flash('Invalid status.', 'danger')
        return redirect(url_for('warranty_detail', warranty_id=warranty_id))
    if new_status == w.status:
        flash('Status is already set to this value.', 'warning')
        return redirect(url_for('warranty_detail', warranty_id=warranty_id))

    old_status = w.status
    w.status   = new_status
    w.updated_at = datetime.utcnow()

    if new_status == WarrantyStatus.CLOSED:
        decision = request.form.get('closure_decision', '')
        if decision not in dict(ClosureDecision.CHOICES):
            flash('A closure decision is required.', 'danger')
            w.status = old_status
            return redirect(url_for('warranty_detail', warranty_id=warranty_id))
        w.closure_decision = decision
        w.closure_comments = comment
        w.closed_at        = datetime.utcnow()
        w.closed_by_id     = current_user.id
        log_activity(w, ActivityType.CLOSED,
            comment=f'Warranty closed — Decision: {ClosureDecision.LABELS[decision]}.'
                    + (f'\n{comment}' if comment else ''),
            old_value=WarrantyStatus.LABELS[old_status],
            new_value=WarrantyStatus.LABELS[new_status])
    elif old_status == WarrantyStatus.CLOSED:
        w.closure_decision = None
        w.closure_comments = None
        w.closed_at        = None
        w.closed_by_id     = None
        log_activity(w, ActivityType.REOPENED,
            comment=f'Warranty re-opened.' + (f'\n{comment}' if comment else ''),
            old_value=WarrantyStatus.LABELS[old_status],
            new_value=WarrantyStatus.LABELS[new_status])
    else:
        log_activity(w, ActivityType.STATUS_CHANGED,
            comment=comment or f'Status moved to «{WarrantyStatus.LABELS[new_status]}».',
            old_value=WarrantyStatus.LABELS[old_status],
            new_value=WarrantyStatus.LABELS[new_status])

    db.session.commit()
    flash(f'Status updated to <strong>{WarrantyStatus.LABELS[new_status]}</strong>.', 'success')
    return redirect(url_for('warranty_detail', warranty_id=warranty_id))

# ─────────────────────────────────────────────────────────────────────────────
# WARRANTY — ADD COMMENT
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/warranty/<int:warranty_id>/add-comment', methods=['POST'])
@login_required
def add_comment(warranty_id):
    w       = Warranty.query.get_or_404(warranty_id)
    comment = request.form.get('comment', '').strip()
    if not comment:
        flash('Comment cannot be empty.', 'warning')
    else:
        log_activity(w, ActivityType.COMMENT_ADDED, comment=comment)
        w.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Comment added.', 'success')
    return redirect(url_for('warranty_detail', warranty_id=warranty_id))

# ─────────────────────────────────────────────────────────────────────────────
# WARRANTY — ASSIGN / REMOVE ENGINEER
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/warranty/<int:warranty_id>/engineer', methods=['POST'])
@login_required
def manage_engineer(warranty_id):
    w    = Warranty.query.get_or_404(warranty_id)
    eng  = User.query.get_or_404(int(request.form.get('engineer_id', 0)))
    action = request.form.get('action', 'assign')

    if action == 'assign' and eng not in w.engineers:
        w.engineers.append(eng)
        log_activity(w, ActivityType.ENGINEER_ASSIGNED,
            comment=f'{eng.full_name} assigned to this warranty.')
        db.session.commit()
        flash(f'{eng.full_name} assigned.', 'success')
    elif action == 'remove' and eng in w.engineers:
        w.engineers.remove(eng)
        log_activity(w, ActivityType.ENGINEER_REMOVED,
            comment=f'{eng.full_name} removed from this warranty.')
        db.session.commit()
        flash(f'{eng.full_name} removed.', 'success')
    else:
        flash('No change made.', 'info')

    return redirect(url_for('warranty_detail', warranty_id=warranty_id))

# ─────────────────────────────────────────────────────────────────────────────
# STATISTICS
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/statistics')
@login_required
def statistics():
    part_numbers = [r[0] for r in
                    db.session.query(Warranty.lru_part_number).distinct()
                    .order_by(Warranty.lru_part_number).all()]
    return render_template('statistics.html',
        customers=Customer.query.filter_by(is_active=True).order_by(Customer.name).all(),
        engineers=User.query.filter_by(is_active=True).order_by(User.last_name).all(),
        part_numbers=part_numbers,
        years=list(range(datetime.utcnow().year - 4, datetime.utcnow().year + 1))[::-1],
    )


@app.route('/api/statistics')
@login_required
def api_statistics():
    customer_id = request.args.get('customer_id', '')
    engineer_id = request.args.get('engineer_id', '')
    part_number = request.args.get('part_number', '')

    q = Warranty.query
    if customer_id:
        q = q.filter(Warranty.customer_id == int(customer_id))
    if engineer_id:
        q = q.filter(Warranty.engineers.any(User.id == int(engineer_id)))
    if part_number:
        q = q.filter(Warranty.lru_part_number == part_number)
    warranties = q.all()

    # ── Monthly trend (last 18 months)
    monthly = defaultdict(int)
    for w in warranties:
        monthly[w.created_at.strftime('%Y-%m')] += 1
    now = datetime.utcnow()
    m_labels, m_data = [], []
    for i in range(17, -1, -1):
        yr, mo = divmod(now.month - 1 - i, 12)
        yr = now.year + yr
        mo = mo + 1
        key = f'{yr}-{mo:02d}'
        m_labels.append(datetime(yr, mo, 1).strftime('%b %y'))
        m_data.append(monthly.get(key, 0))

    # ── By status
    status_labels = [v for _, v in WarrantyStatus.CHOICES]
    status_data   = [sum(1 for w in warranties if w.status == k)
                     for k, _ in WarrantyStatus.CHOICES]
    status_colors = [WarrantyStatus.HEX[k] for k, _ in WarrantyStatus.CHOICES]

    # ── Closure decisions
    closed = [w for w in warranties if w.status == WarrantyStatus.CLOSED]
    dec_labels = [v for _, v in ClosureDecision.CHOICES]
    dec_data   = [sum(1 for w in closed if w.closure_decision == k)
                  for k, _ in ClosureDecision.CHOICES]
    dec_colors = [ClosureDecision.HEX[k] for k, _ in ClosureDecision.CHOICES]

    # ── Top parts
    pn_cnt = defaultdict(int)
    for w in warranties:
        pn_cnt[w.lru_part_number] += 1
    top_pns = sorted(pn_cnt.items(), key=lambda x: x[1], reverse=True)[:10]

    # ── By customer
    cust_cnt = defaultdict(int)
    for w in warranties:
        cust_cnt[w.customer.name if w.customer else 'Unknown'] += 1
    cust_sorted = sorted(cust_cnt.items(), key=lambda x: x[1], reverse=True)

    # ── By engineer
    eng_cnt = defaultdict(int)
    for w in warranties:
        for e in w.engineers:
            eng_cnt[e.full_name] += 1
    eng_sorted = sorted(eng_cnt.items(), key=lambda x: x[1], reverse=True)

    # ── KPIs
    total   = len(warranties)
    n_open  = sum(1 for w in warranties if w.status != WarrantyStatus.CLOSED)
    n_closed = len(closed)
    acc_rate = (round(sum(1 for w in closed
                          if w.closure_decision == ClosureDecision.ACCEPTED)
                      / n_closed * 100, 1)
                if n_closed else 0)

    return jsonify(
        monthly      = {'labels': m_labels,   'data': m_data},
        by_status    = {'labels': status_labels, 'data': status_data, 'colors': status_colors},
        by_decision  = {'labels': dec_labels,  'data': dec_data,   'colors': dec_colors},
        top_parts    = {'labels': [p[0] for p in top_pns],  'data': [p[1] for p in top_pns]},
        by_customer  = {'labels': [c[0] for c in cust_sorted], 'data': [c[1] for c in cust_sorted]},
        by_engineer  = {'labels': [e[0] for e in eng_sorted],  'data': [e[1] for e in eng_sorted]},
        kpi          = {'total': total, 'open': n_open, 'closed': n_closed, 'acc_rate': acc_rate},
    )

# ─────────────────────────────────────────────────────────────────────────────
# CLI — DATABASE INIT & SEED
# ─────────────────────────────────────────────────────────────────────────────
@app.cli.command('init-db')
def init_db_cmd():
    """Create tables and seed reference data."""
    _init_db()
    print("✓ Database initialised.")
    print("  Admin    : admin / Admin123!")
    print("  Engineers: j.smith, m.wilson … / Engineer1!")


@app.cli.command('seed-warranties')
def seed_warranties():
    """Populate the database with realistic sample warranties."""
    import random
    admin     = User.query.filter_by(username='admin').first()
    customers = Customer.query.all()
    engineers = User.query.filter(User.role == 'engineer').all()
    if not (admin and customers and engineers):
        print("Run 'flask init-db' first.")
        return

    PARTS = [
        ('P145-AHRS-0210', 'Attitude & Heading Reference System',     '34-21'),
        ('P145-FMC-0614',  'Flight Management Computer',              '34-61'),
        ('P145-EIU-0322',  'Engine Interface Unit',                   '73-22'),
        ('P145-IDG-0411',  'Integrated Drive Generator',              '24-11'),
        ('P145-VHF-0234',  'VHF Communication Unit',                  '23-11'),
        ('P145-TCAS-0443', 'TCAS II Processor',                       '34-43'),
        ('P145-APU-0049',  'APU Control Unit',                        '49-11'),
        ('P145-WXR-0844',  'Weather Radar Transceiver',               '34-41'),
        ('P145-PSEU-0329', 'Proximity Switch Electronics Unit',       '32-09'),
        ('P145-ADIRU-034', 'Air Data Inertial Reference Unit',        '34-15'),
    ]
    DEFECTS = [
        'Unit failed Built-In Test on power-up. No valid output signals observed.',
        'Intermittent fault reported by flight crew. BITE confirms LRU unserviceable.',
        'Over-temperature warning during operation. Unit shut down automatically.',
        'Loss of digital bus communication with avionics systems.',
        'Physical damage on connector P1 — bent contacts observed.',
        'Software configuration mismatch detected during scheduled maintenance check.',
        'Unit fails to complete initialisation sequence after cold soak test.',
        'Erroneous data output recorded on QAR. Cross-check with backup system failed.',
        'High current consumption fault flag. Repeated thermal protection trip.',
    ]

    statuses   = [WarrantyStatus.OPEN, WarrantyStatus.WORKSHOP,
                  WarrantyStatus.ENGINEERING, WarrantyStatus.CLOSED,
                  WarrantyStatus.CLOSED]  # more closed for realism
    decisions  = [ClosureDecision.ACCEPTED, ClosureDecision.PARTIALLY_ACCEPTED,
                  ClosureDecision.REJECTED, ClosureDecision.ACCEPTED]

    for _ in range(40):
        part     = random.choice(PARTS)
        customer = random.choice(customers)
        days_ago = random.randint(10, 540)
        start_dt = datetime.utcnow() - timedelta(days=days_ago)
        start_d  = start_dt.date()
        status   = random.choice(statuses)

        w = Warranty(
            warranty_number         = Warranty.generate_warranty_number(),
            lru_part_number         = part[0],
            lru_serial_number       = f'SN-{random.randint(10000, 99999)}',
            lru_description         = part[1],
            customer_id             = customer.id,
            current_mco             = f'MCO-{random.randint(2022,2025)}-{random.randint(1000,9999)}',
            former_mco              = f'MCO-{random.randint(2018,2022)}-{random.randint(1000,9999)}',
            former_arc_date         = start_d - timedelta(days=random.randint(90, 900)),
            defect_date             = start_d - timedelta(days=random.randint(5, 60)),
            adjudication_start_date = start_d,
            installation_date       = start_d - timedelta(days=random.randint(60, 400)),
            observed_defect         = random.choice(DEFECTS),
            reason_for_removal      = 'Unscheduled removal due to in-flight fault indication.',
            ata_chapter             = part[2],
            tsi                     = round(random.uniform(50, 6000),  1),
            tso                     = round(random.uniform(100, 15000), 1),
            flight_cycles_since_installation = random.randint(10, 3000),
            status                  = status,
            created_by_id           = admin.id,
            created_at              = start_dt,
            updated_at              = start_dt,
        )

        if status == WarrantyStatus.CLOSED:
            decision         = random.choice(decisions)
            w.closure_decision = decision
            w.closed_at      = start_dt + timedelta(days=random.randint(10, 90))
            w.closed_by_id   = admin.id
            w.closure_comments = ('Investigation complete. '
                + ('Root-cause identified as manufacturing defect — within warranty scope.'
                   if decision == ClosureDecision.ACCEPTED else
                   'Partial damage attributable to warranty; installation damage excluded.'
                   if decision == ClosureDecision.PARTIALLY_ACCEPTED else
                   'Damage caused by foreign object / improper installation. Warranty not applicable.'))

        db.session.add(w)
        db.session.flush()

        assigned = random.sample(engineers, k=random.randint(1, min(3, len(engineers))))
        for eng in assigned:
            w.engineers.append(eng)

        # Seed activity log
        a1 = WarrantyActivity(warranty_id=w.id, user_id=admin.id,
                              activity_type=ActivityType.CREATED,
                              comment=f'Warranty {w.warranty_number} created.',
                              timestamp=start_dt)
        db.session.add(a1)

        if status in [WarrantyStatus.WORKSHOP, WarrantyStatus.ENGINEERING, WarrantyStatus.CLOSED]:
            a2 = WarrantyActivity(
                warranty_id=w.id, user_id=random.choice(engineers).id,
                activity_type=ActivityType.STATUS_CHANGED,
                comment='Unit received in workshop. Visual inspection initiated.',
                old_value='Open', new_value='Under Workshop Investigation',
                timestamp=start_dt + timedelta(days=random.randint(1, 5)))
            db.session.add(a2)

        if status in [WarrantyStatus.ENGINEERING, WarrantyStatus.CLOSED]:
            a3 = WarrantyActivity(
                warranty_id=w.id, user_id=random.choice(engineers).id,
                activity_type=ActivityType.COMMENT_ADDED,
                comment='Workshop test report completed. Root-cause identified. '
                        'Forwarding to engineering for warranty decision.',
                timestamp=start_dt + timedelta(days=random.randint(6, 20)))
            db.session.add(a3)

        if status == WarrantyStatus.CLOSED:
            a4 = WarrantyActivity(
                warranty_id=w.id, user_id=admin.id,
                activity_type=ActivityType.CLOSED,
                comment=w.closure_comments,
                old_value='Under Engineering Review', new_value='Closed',
                timestamp=w.closed_at)
            db.session.add(a4)

    db.session.commit()
    print("✓ 40 sample warranty records created.")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
# Initialise DB at startup (tables + seed data) for WSGI servers like Gunicorn
with app.app_context():
    _init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
