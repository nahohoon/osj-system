"""
오성정공 스마트 생산·금형·품질 통합관리시스템
DB 스키마 (SQLite + Flask-SQLAlchemy)
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ─────────────────────────────────────────────
# 1. 기준정보 (Master Data)
# ─────────────────────────────────────────────

class Product(db.Model):
    """품목 마스터 (브라켓 제품)"""
    __tablename__ = 'product'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(30), unique=True, nullable=False)  # 품번
    name        = db.Column(db.String(100), nullable=False)              # 품명
    customer    = db.Column(db.String(50), default='현대자동차')          # 납품처
    unit        = db.Column(db.String(10), default='EA')
    std_cycle   = db.Column(db.Float, default=0.0)   # 표준사이클(초/개)
    usl         = db.Column(db.Float)                # 치수 상한
    lsl         = db.Column(db.Float)                # 치수 하한
    nominal     = db.Column(db.Float)                # 기준치수
    note        = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.now)
    # Relations
    bom_items   = db.relationship('BomItem',    backref='product', lazy=True, cascade='all,delete')
    routings    = db.relationship('Routing',    backref='product', lazy=True, cascade='all,delete')
    prod_plans  = db.relationship('ProductionPlan', backref='product', lazy=True)
    inspections = db.relationship('Inspection', backref='product', lazy=True)

class Material(db.Model):
    """자재 마스터 (소재/원자재)"""
    __tablename__ = 'material'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(30), unique=True, nullable=False)
    name        = db.Column(db.String(100), nullable=False)
    spec        = db.Column(db.String(100))   # 규격
    unit        = db.Column(db.String(10), default='kg')
    unit_weight = db.Column(db.Float, default=0.0)  # 개당 중량
    stock_qty   = db.Column(db.Float, default=0.0)
    safety_qty  = db.Column(db.Float, default=0.0)  # 안전재고
    note        = db.Column(db.Text)

class WorkCenter(db.Model):
    """작업장/공정설비"""
    __tablename__ = 'workcenter'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(20), unique=True, nullable=False)
    name        = db.Column(db.String(80), nullable=False)
    machine_no  = db.Column(db.String(30))   # 설비번호
    capacity    = db.Column(db.Integer, default=480)  # 일 가동시간(분)
    note        = db.Column(db.Text)

# ─────────────────────────────────────────────
# 2. 생산기술 / 공정
# ─────────────────────────────────────────────

class BomItem(db.Model):
    """BOM (자재소요량)"""
    __tablename__ = 'bom_item'
    id          = db.Column(db.Integer, primary_key=True)
    product_id  = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    qty_per     = db.Column(db.Float, default=1.0)  # 제품 1개당 소요량
    loss_rate   = db.Column(db.Float, default=0.0)  # 로스율(%)
    note        = db.Column(db.Text)
    material    = db.relationship('Material')

class Routing(db.Model):
    """공정 Routing (공정순서)"""
    __tablename__ = 'routing'
    id              = db.Column(db.Integer, primary_key=True)
    product_id      = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    step_no         = db.Column(db.Integer, nullable=False)   # 공정 순번
    step_name       = db.Column(db.String(80), nullable=False) # 공정명
    workcenter_id   = db.Column(db.Integer, db.ForeignKey('workcenter.id'))
    std_time        = db.Column(db.Float, default=0.0)  # 표준공수(분/100개)
    mold_id         = db.Column(db.Integer, db.ForeignKey('mold.id'), nullable=True)
    note            = db.Column(db.Text)
    workcenter      = db.relationship('WorkCenter')
    mold            = db.relationship('Mold', backref='routings')

# ─────────────────────────────────────────────
# 3. 금형 관리
# ─────────────────────────────────────────────

class Mold(db.Model):
    """금형 마스터"""
    __tablename__ = 'mold'
    id              = db.Column(db.Integer, primary_key=True)
    code            = db.Column(db.String(30), unique=True, nullable=False)
    name            = db.Column(db.String(100), nullable=False)
    product_code    = db.Column(db.String(30))        # 적용 품번
    owner           = db.Column(db.String(30), default='현대자동차')  # 금형 소유자
    material        = db.Column(db.String(50))        # 금형 재질
    cavity          = db.Column(db.Integer, default=1) # 캐비티 수
    life_shot       = db.Column(db.Integer, default=500000)  # 수명 타수
    pm_interval     = db.Column(db.Integer, default=50000)   # PM 주기 (타수)
    current_shot    = db.Column(db.Integer, default=0)       # 누적 타수
    last_pm_shot    = db.Column(db.Integer, default=0)       # 최종 PM 시점 타수
    status          = db.Column(db.String(20), default='정상')  # 정상/점검중/수리중
    location        = db.Column(db.String(50))
    registered_date = db.Column(db.String(20))
    note            = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=datetime.now)
    # Relations
    maint_records   = db.relationship('MoldMaintenance', backref='mold', lazy=True, cascade='all,delete')

    @property
    def life_rate(self):
        """수명 사용률(%)"""
        if self.life_shot == 0:
            return 0.0
        return round(self.current_shot / self.life_shot * 100, 1)

    @property
    def next_pm_shot(self):
        """다음 PM 타수"""
        return self.last_pm_shot + self.pm_interval

    @property
    def pm_remaining(self):
        """PM 잔여 타수"""
        return max(0, self.next_pm_shot - self.current_shot)

    @property
    def pm_alert(self):
        """PM 알림 여부 (잔여 5000 이하)"""
        return self.pm_remaining <= 5000

class MoldMaintenance(db.Model):
    """금형 정비 이력"""
    __tablename__ = 'mold_maintenance'
    id          = db.Column(db.Integer, primary_key=True)
    mold_id     = db.Column(db.Integer, db.ForeignKey('mold.id'), nullable=False)
    maint_date  = db.Column(db.String(20), nullable=False)
    maint_type  = db.Column(db.String(30))   # 예방정비/긴급수리/정기점검
    shot_at     = db.Column(db.Integer)      # 정비 시점 타수
    content     = db.Column(db.Text)         # 정비 내용
    worker      = db.Column(db.String(30))
    cost        = db.Column(db.Integer, default=0)
    next_plan   = db.Column(db.String(20))   # 차기 정비 예정일
    created_at  = db.Column(db.DateTime, default=datetime.now)

# ─────────────────────────────────────────────
# 4. 생산 운영
# ─────────────────────────────────────────────

class ProductionPlan(db.Model):
    """생산계획"""
    __tablename__ = 'production_plan'
    id          = db.Column(db.Integer, primary_key=True)
    plan_date   = db.Column(db.String(20), nullable=False)
    product_id  = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    mold_id     = db.Column(db.Integer, db.ForeignKey('mold.id'))
    plan_qty    = db.Column(db.Integer, default=0)
    shift       = db.Column(db.String(10), default='주간')  # 주간/야간
    status      = db.Column(db.String(20), default='계획')  # 계획/진행/완료
    note        = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.now)
    mold        = db.relationship('Mold')
    work_orders = db.relationship('WorkOrder', backref='plan', lazy=True, cascade='all,delete')

class WorkOrder(db.Model):
    """작업지시"""
    __tablename__ = 'work_order'
    id          = db.Column(db.Integer, primary_key=True)
    wo_no       = db.Column(db.String(30), unique=True, nullable=False)  # 작업지시번호
    plan_id     = db.Column(db.Integer, db.ForeignKey('production_plan.id'), nullable=False)
    workcenter_id = db.Column(db.Integer, db.ForeignKey('workcenter.id'))
    ordered_qty = db.Column(db.Integer, default=0)
    status      = db.Column(db.String(20), default='대기')  # 대기/진행/완료/취소
    start_dt    = db.Column(db.String(30))
    end_dt      = db.Column(db.String(30))
    note        = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.now)
    workcenter  = db.relationship('WorkCenter')
    results     = db.relationship('ProductionResult', backref='work_order', lazy=True, cascade='all,delete')

class ProductionResult(db.Model):
    """생산실적 (LOT 포함)"""
    __tablename__ = 'production_result'
    id          = db.Column(db.Integer, primary_key=True)
    lot_no      = db.Column(db.String(30), nullable=False)   # LOT 번호
    wo_id       = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    result_date = db.Column(db.String(20), nullable=False)
    good_qty    = db.Column(db.Integer, default=0)    # 양품수
    defect_qty  = db.Column(db.Integer, default=0)    # 불량수
    total_qty   = db.Column(db.Integer, default=0)    # 총 생산수
    shot_count  = db.Column(db.Integer, default=0)    # 이번 LOT 타수
    worker      = db.Column(db.String(30))
    note        = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.now)

class DefectRecord(db.Model):
    """불량 등록"""
    __tablename__ = 'defect_record'
    id          = db.Column(db.Integer, primary_key=True)
    lot_no      = db.Column(db.String(30))
    result_id   = db.Column(db.Integer, db.ForeignKey('production_result.id'))
    product_id  = db.Column(db.Integer, db.ForeignKey('product.id'))
    mold_id     = db.Column(db.Integer, db.ForeignKey('mold.id'))
    defect_date = db.Column(db.String(20), nullable=False)
    defect_type = db.Column(db.String(50))   # 치수불량/외관불량/균열/버 등
    defect_qty  = db.Column(db.Integer, default=1)
    cause       = db.Column(db.Text)         # 불량 원인
    action      = db.Column(db.Text)         # 조치사항
    worker      = db.Column(db.String(30))
    created_at  = db.Column(db.DateTime, default=datetime.now)
    product     = db.relationship('Product')
    mold        = db.relationship('Mold')
    result      = db.relationship('ProductionResult', backref=db.backref('defect_records', lazy=True))

# ─────────────────────────────────────────────
# 5. 품질혁신 (순회검사)
# ─────────────────────────────────────────────

class Inspection(db.Model):
    """순회검사 (대표 직접 검사 포함)"""
    __tablename__ = 'inspection'
    id              = db.Column(db.Integer, primary_key=True)
    insp_no         = db.Column(db.String(30), unique=True)   # 검사번호
    insp_date       = db.Column(db.String(20), nullable=False)
    insp_time       = db.Column(db.String(10))
    product_id      = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    mold_id         = db.Column(db.Integer, db.ForeignKey('mold.id'))
    lot_no          = db.Column(db.String(30))
    inspector       = db.Column(db.String(30), default='대표')
    insp_type       = db.Column(db.String(20), default='순회검사')  # 순회검사/초품검사/최종검사
    tool_used       = db.Column(db.String(50), default='버니어캘리퍼스')
    overall_result  = db.Column(db.String(10))   # PASS/FAIL
    note            = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=datetime.now)
    mold            = db.relationship('Mold')
    items           = db.relationship('InspectionItem', backref='inspection', lazy=True, cascade='all,delete')

class InspectionItem(db.Model):
    """검사 항목별 측정값"""
    __tablename__ = 'inspection_item'
    id              = db.Column(db.Integer, primary_key=True)
    inspection_id   = db.Column(db.Integer, db.ForeignKey('inspection.id'), nullable=False)
    item_name       = db.Column(db.String(80), nullable=False)  # 검사 항목명
    nominal         = db.Column(db.Float)    # 기준치
    usl             = db.Column(db.Float)    # 상한
    lsl             = db.Column(db.Float)    # 하한
    measured        = db.Column(db.Float)    # 실측값
    result          = db.Column(db.String(10))  # PASS/FAIL
    note            = db.Column(db.Text)
