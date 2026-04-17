"""
오성정공 금형기반 스마트 생산품질 관리시스템
─────────────────────────────────────────────
컨셉: 금형 상태 데이터 기반으로 생산·품질 정보를 통합 관리하여
      자동차 프레스 부품 제조현장의 품질혁신과 예방정비를 지원하는
      금형기반 스마트 생산품질 관리시스템

메인 Flask 애플리케이션 (app.py)
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, Product, Mold, MoldMaintenance
from models import ProductionPlan, WorkOrder, ProductionResult, DefectRecord, Inspection, InspectionItem
from datetime import datetime, timedelta
from collections import defaultdict, Counter

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///osj_integrated.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'osj2025secretkey'
db.init_app(app)

# ─── DB 초기화 ─────────────────────────────────
@app.before_request
def create_tables():
    db.create_all()

# ─── 전역 컨텍스트 ─────────────────────────────
@app.context_processor
def inject_common():
    pm_alerts = [m for m in Mold.query.filter_by(status='정상').all() if m.pm_alert]
    return dict(
        pm_alert_count=len(pm_alerts),
        today=datetime.today().strftime('%Y-%m-%d'),
        SYSTEM_NAME='오성정공 금형기반 스마트 생산품질 관리시스템'
    )

# ═══════════════════════════════════════════════
# 대시보드 — 금형 상태 × 생산품질 통합 현황
# ═══════════════════════════════════════════════
@app.route('/')
def dashboard():
    today = datetime.today().strftime('%Y-%m-%d')

    # ── 오늘 생산 KPI
    today_results = ProductionResult.query.filter_by(result_date=today).all()
    today_good    = sum(r.good_qty   for r in today_results)
    today_defect  = sum(r.defect_qty for r in today_results)
    today_total   = sum(r.total_qty  for r in today_results)
    defect_rate   = round(today_defect / today_total * 100, 2) if today_total else 0

    # ── 금형 PM 알림
    all_molds = Mold.query.all()
    pm_molds  = [m for m in all_molds if m.pm_alert]

    # ── 최근 순회검사
    recent_insp = Inspection.query.order_by(Inspection.id.desc()).limit(5).all()

    # ── 최근 불량
    recent_defects = DefectRecord.query.order_by(DefectRecord.id.desc()).limit(5).all()

    # ── 진행중 작업지시
    active_wo = WorkOrder.query.filter_by(status='진행').all()

    # ── 주간 생산 추이 (7일)
    trend = []
    for i in range(6, -1, -1):
        d = (datetime.today() - timedelta(days=i)).strftime('%Y-%m-%d')
        rs = ProductionResult.query.filter_by(result_date=d).all()
        trend.append({'date': d[-5:],
                      'good':   sum(r.good_qty   for r in rs),
                      'defect': sum(r.defect_qty for r in rs)})

    # ── 금형별 최근 불량률 (금형↔품질 연계 핵심 KPI)
    mold_quality = []
    for m in Mold.query.all():
        defects = DefectRecord.query.filter_by(mold_id=m.id).all()
        results = []
        for d in defects:
            if d.result:
                results.append(d.result.total_qty)
        total_prod = sum(results) if results else 0
        total_def  = sum(d.defect_qty for d in defects)
        dr = round(total_def / total_prod * 100, 2) if total_prod > 0 else 0
        mold_quality.append({
            'name': m.code, 'life_rate': m.life_rate,
            'defect_rate': dr, 'pm_alert': m.pm_alert, 'status': m.status
        })

    return render_template('dashboard.html',
        today_good=today_good, today_defect=today_defect,
        today_total=today_total, defect_rate=defect_rate,
        pm_molds=pm_molds, recent_insp=recent_insp,
        recent_defects=recent_defects, active_wo=active_wo,
        trend=trend, mold_quality=mold_quality,
        mold_count=len(all_molds))

# ═══════════════════════════════════════════════
# 기준정보 — 품목 (치수 기준값 중심, 단순화)
# ═══════════════════════════════════════════════
@app.route('/product')
def product_list():
    return render_template('product_list.html', items=Product.query.order_by(Product.code).all())

@app.route('/product/new', methods=['GET','POST'])
def product_new():
    if request.method == 'POST':
        p = Product(
            code=request.form['code'], name=request.form['name'],
            customer=request.form.get('customer','현대자동차'),
            unit=request.form.get('unit','EA'),
            std_cycle=_f(request.form.get('std_cycle')) or 0,
            usl=_f(request.form.get('usl')), lsl=_f(request.form.get('lsl')),
            nominal=_f(request.form.get('nominal')), note=request.form.get('note',''))
        db.session.add(p); db.session.commit()
        flash('품목이 등록되었습니다.', 'success')
        return redirect(url_for('product_list'))
    return render_template('product_form.html', item=None)

@app.route('/product/<int:pid>/edit', methods=['GET','POST'])
def product_edit(pid):
    p = Product.query.get_or_404(pid)
    if request.method == 'POST':
        p.code=request.form['code']; p.name=request.form['name']
        p.customer=request.form.get('customer','현대자동차')
        p.std_cycle=_f(request.form.get('std_cycle')) or 0
        p.usl=_f(request.form.get('usl')); p.lsl=_f(request.form.get('lsl'))
        p.nominal=_f(request.form.get('nominal')); p.note=request.form.get('note','')
        db.session.commit(); flash('수정되었습니다.', 'success')
        return redirect(url_for('product_list'))
    return render_template('product_form.html', item=p)

@app.route('/product/<int:pid>/delete', methods=['POST'])
def product_delete(pid):
    db.session.delete(Product.query.get_or_404(pid)); db.session.commit()
    flash('삭제되었습니다.', 'warning'); return redirect(url_for('product_list'))

# API: 품목 치수기준 조회 (순회검사 자동 연동)
@app.route('/api/product/<int:pid>/dims')
def api_product_dims(pid):
    p = Product.query.get_or_404(pid)
    return jsonify({'nominal': p.nominal, 'usl': p.usl, 'lsl': p.lsl,
                    'name': p.name, 'code': p.code})

# ═══════════════════════════════════════════════
# 금형 관리 — 핵심 모듈
# ═══════════════════════════════════════════════
@app.route('/mold')
def mold_list():
    sf = request.args.get('status', '')
    q  = Mold.query.filter_by(status=sf) if sf else Mold.query
    molds    = q.order_by(Mold.code).all()
    pm_molds = [m for m in Mold.query.all() if m.pm_alert]
    return render_template('mold_list.html', molds=molds, pm_molds=pm_molds, status_filter=sf)

@app.route('/mold/new', methods=['GET','POST'])
def mold_new():
    if request.method == 'POST':
        m = Mold(code=request.form['code'], name=request.form['name'],
            product_code=request.form.get('product_code',''),
            owner=request.form.get('owner','현대자동차'),
            material=request.form.get('material',''),
            cavity=int(request.form.get('cavity',1) or 1),
            life_shot=int(request.form.get('life_shot',500000) or 500000),
            pm_interval=int(request.form.get('pm_interval',50000) or 50000),
            current_shot=int(request.form.get('current_shot',0) or 0),
            last_pm_shot=int(request.form.get('last_pm_shot',0) or 0),
            status=request.form.get('status','정상'),
            location=request.form.get('location',''),
            registered_date=request.form.get('registered_date',''),
            note=request.form.get('note',''))
        db.session.add(m); db.session.commit()
        flash('금형이 등록되었습니다.', 'success')
        return redirect(url_for('mold_list'))
    return render_template('mold_form.html', item=None)

@app.route('/mold/<int:mid>')
def mold_detail(mid):
    mold   = Mold.query.get_or_404(mid)
    maints = MoldMaintenance.query.filter_by(mold_id=mid).order_by(
             MoldMaintenance.maint_date.desc()).all()
    # 이 금형의 최근 불량·검사
    recent_defects = DefectRecord.query.filter_by(mold_id=mid).order_by(
                     DefectRecord.id.desc()).limit(10).all()
    recent_insp    = Inspection.query.filter_by(mold_id=mid).order_by(
                     Inspection.id.desc()).limit(10).all()
    # 금형 타수별 불량률 추이 (최근 10개 실적)
    shot_trend = _mold_shot_quality(mid)
    return render_template('mold_detail.html', mold=mold, maints=maints,
                           recent_defects=recent_defects, recent_insp=recent_insp,
                           shot_trend=shot_trend)

@app.route('/mold/<int:mid>/edit', methods=['GET','POST'])
def mold_edit(mid):
    m = Mold.query.get_or_404(mid)
    if request.method == 'POST':
        m.code=request.form['code']; m.name=request.form['name']
        m.product_code=request.form.get('product_code','')
        m.owner=request.form.get('owner','현대자동차')
        m.material=request.form.get('material','')
        m.cavity=int(request.form.get('cavity',1) or 1)
        m.life_shot=int(request.form.get('life_shot',500000) or 500000)
        m.pm_interval=int(request.form.get('pm_interval',50000) or 50000)
        m.status=request.form.get('status','정상')
        m.location=request.form.get('location','')
        m.registered_date=request.form.get('registered_date','')
        m.note=request.form.get('note','')
        db.session.commit(); flash('수정되었습니다.', 'success')
        return redirect(url_for('mold_detail', mid=mid))
    return render_template('mold_form.html', item=m)

@app.route('/mold/<int:mid>/shot', methods=['POST'])
def mold_shot_update(mid):
    mold = Mold.query.get_or_404(mid)
    mold.current_shot = int(request.form.get('current_shot', mold.current_shot))
    db.session.commit(); flash('타수가 업데이트되었습니다.', 'success')
    return redirect(url_for('mold_detail', mid=mid))

# 금형 정비
@app.route('/mold/<int:mid>/maint/new', methods=['GET','POST'])
def maint_new(mid):
    mold = Mold.query.get_or_404(mid)
    if request.method == 'POST':
        mn = MoldMaintenance(mold_id=mid,
            maint_date=request.form['maint_date'],
            maint_type=request.form.get('maint_type','예방정비'),
            shot_at=int(request.form.get('shot_at', mold.current_shot) or 0),
            content=request.form.get('content',''),
            worker=request.form.get('worker',''),
            cost=int(request.form.get('cost',0) or 0),
            next_plan=request.form.get('next_plan',''))
        if request.form.get('maint_type') in ['예방정비','정기점검']:
            mold.last_pm_shot = mn.shot_at
        db.session.add(mn); db.session.commit()
        flash('정비이력이 등록되었습니다.', 'success')
        return redirect(url_for('mold_detail', mid=mid))
    return render_template('maint_form.html', mold=mold)

@app.route('/maint/<int:mnid>/delete', methods=['POST'])
def maint_delete(mnid):
    mn = MoldMaintenance.query.get_or_404(mnid); mid = mn.mold_id
    db.session.delete(mn); db.session.commit()
    flash('삭제되었습니다.', 'warning')
    return redirect(url_for('mold_detail', mid=mid))
# ─────────────────────────────────────────────
# 정비이력 전체 목록 (추가)
# ─────────────────────────────────────────────
@app.route('/maintenance')
def maintenance_list():
    maints = MoldMaintenance.query.order_by(
        MoldMaintenance.maint_date.desc()
    ).all()

    total = len(maints)

    from collections import Counter
    type_cnt = Counter(m.maint_type for m in maints if m.maint_type)

    return render_template(
        'maintenance_list.html',
        maints=maints,
        total=total,
        type_labels=list(type_cnt.keys()),
        type_data=list(type_cnt.values())
    )
# ═══════════════════════════════════════════════
# 생산관리 — 생산계획
# ═══════════════════════════════════════════════
@app.route('/plan')
def plan_list():
    df = request.args.get('date', datetime.today().strftime('%Y-%m'))
    plans = ProductionPlan.query.filter(
        ProductionPlan.plan_date.like(f'{df}%')
    ).order_by(ProductionPlan.plan_date.desc()).all()
    return render_template('plan_list.html', plans=plans, date_filter=df)

@app.route('/plan/new', methods=['GET','POST'])
def plan_new():
    products = Product.query.order_by(Product.code).all()
    molds    = Mold.query.filter_by(status='정상').all()
    if request.method == 'POST':
        p = ProductionPlan(
            plan_date=request.form['plan_date'],
            product_id=int(request.form['product_id']),
            mold_id=_i(request.form.get('mold_id')),
            plan_qty=int(request.form.get('plan_qty',0)),
            shift=request.form.get('shift','주간'),
            note=request.form.get('note',''))
        db.session.add(p); db.session.commit()
        flash('생산계획이 등록되었습니다.', 'success')
        return redirect(url_for('plan_list'))
    return render_template('plan_form.html', item=None, products=products, molds=molds)

@app.route('/plan/<int:pid>/edit', methods=['GET','POST'])
def plan_edit(pid):
    p       = ProductionPlan.query.get_or_404(pid)
    products= Product.query.order_by(Product.code).all()
    molds   = Mold.query.filter_by(status='정상').all()
    if request.method == 'POST':
        p.plan_date =request.form['plan_date']
        p.product_id=int(request.form['product_id'])
        p.mold_id   =_i(request.form.get('mold_id'))
        p.plan_qty  =int(request.form.get('plan_qty',0))
        p.shift     =request.form.get('shift','주간')
        p.status    =request.form.get('status','계획')
        p.note      =request.form.get('note','')
        db.session.commit(); flash('수정되었습니다.', 'success')
        return redirect(url_for('plan_list'))
    return render_template('plan_form.html', item=p, products=products, molds=molds)

# ═══════════════════════════════════════════════
# 생산관리 — 작업지시
# ═══════════════════════════════════════════════
@app.route('/workorder')
def wo_list():
    sf  = request.args.get('status','')
    q   = WorkOrder.query.filter_by(status=sf) if sf else WorkOrder.query
    wos = q.order_by(WorkOrder.id.desc()).all()
    return render_template('wo_list.html', wos=wos, status_f=sf)

@app.route('/workorder/new', methods=['GET','POST'])
def wo_new():
    plans = ProductionPlan.query.filter(ProductionPlan.status != '완료').order_by(
            ProductionPlan.plan_date.desc()).all()
    if request.method == 'POST':
        wo_no = 'WO' + datetime.now().strftime('%Y%m%d%H%M%S')
        w = WorkOrder(wo_no=wo_no,
            plan_id=int(request.form['plan_id']),
            ordered_qty=int(request.form.get('ordered_qty',0)),
            start_dt=request.form.get('start_dt',''),
            note=request.form.get('note',''))
        db.session.add(w); db.session.commit()
        flash(f'작업지시 {wo_no} 생성되었습니다.', 'success')
        return redirect(url_for('wo_list'))
    return render_template('wo_form.html', item=None, plans=plans)

@app.route('/workorder/<int:wid>')
def wo_detail(wid):
    w = WorkOrder.query.get_or_404(wid)
    return render_template('wo_detail.html', wo=w)

@app.route('/workorder/<int:wid>/status', methods=['POST'])
def wo_status(wid):
    w = WorkOrder.query.get_or_404(wid)
    w.status = request.form.get('status', w.status)
    if w.status == '완료':
        w.end_dt = datetime.now().strftime('%Y-%m-%d %H:%M')
        w.plan.status = '완료'
    elif w.status == '진행':
        w.start_dt = datetime.now().strftime('%Y-%m-%d %H:%M')
        w.plan.status = '진행'
    db.session.commit(); flash('상태가 변경되었습니다.', 'success')
    return redirect(url_for('wo_list'))

# ═══════════════════════════════════════════════
# 생산관리 — 생산실적 / LOT
# ═══════════════════════════════════════════════
@app.route('/result')
def result_list():
    df = request.args.get('date', datetime.today().strftime('%Y-%m'))
    results = ProductionResult.query.filter(
        ProductionResult.result_date.like(f'{df}%')
    ).order_by(ProductionResult.id.desc()).all()
    return render_template('result_list.html', results=results, date_filter=df)

@app.route('/result/new', methods=['GET','POST'])
def result_new():
    wos = WorkOrder.query.filter(WorkOrder.status.in_(['진행','대기'])).all()
    if request.method == 'POST':
        wo_id      = int(request.form['wo_id'])
        good_qty   = int(request.form.get('good_qty',0))
        defect_qty = int(request.form.get('defect_qty',0))
        total_qty  = good_qty + defect_qty
        shot_cnt   = int(request.form.get('shot_count',0) or total_qty)
        lot_no     = 'LOT' + datetime.now().strftime('%Y%m%d%H%M%S')
        r = ProductionResult(lot_no=lot_no, wo_id=wo_id,
            result_date=request.form.get('result_date', datetime.today().strftime('%Y-%m-%d')),
            good_qty=good_qty, defect_qty=defect_qty, total_qty=total_qty,
            shot_count=shot_cnt, worker=request.form.get('worker',''),
            note=request.form.get('note',''))
        db.session.add(r); db.session.commit()
        # 금형 타수 자동 증가
        wo = WorkOrder.query.get(wo_id)
        if wo and wo.plan and wo.plan.mold_id:
            mold = Mold.query.get(wo.plan.mold_id)
            if mold:
                mold.current_shot += shot_cnt
                db.session.commit()
        flash(f'실적 등록 완료. LOT: {lot_no}', 'success')
        return redirect(url_for('result_list'))
    return render_template('result_form.html', item=None, wos=wos)

# ═══════════════════════════════════════════════
# 생산관리 — 불량 등록
# ═══════════════════════════════════════════════
@app.route('/defect')
def defect_list():
    defects = DefectRecord.query.order_by(DefectRecord.id.desc()).limit(100).all()
    tc = Counter(d.defect_type for d in defects if d.defect_type)
    return render_template('defect_list.html', defects=defects,
                           trend_labels=list(tc.keys())[:8],
                           trend_data=[tc[k] for k in list(tc.keys())[:8]])

@app.route('/defect/new', methods=['GET','POST'])
def defect_new():
    products = Product.query.order_by(Product.code).all()
    molds    = Mold.query.order_by(Mold.code).all()
    results  = ProductionResult.query.order_by(ProductionResult.id.desc()).limit(50).all()
    if request.method == 'POST':
        d = DefectRecord(
            lot_no=request.form.get('lot_no',''),
            result_id=_i(request.form.get('result_id')),
            product_id=_i(request.form.get('product_id')),
            mold_id=_i(request.form.get('mold_id')),
            defect_date=request.form.get('defect_date', datetime.today().strftime('%Y-%m-%d')),
            defect_type=request.form.get('defect_type',''),
            defect_qty=int(request.form.get('defect_qty',1)),
            cause=request.form.get('cause',''),
            action=request.form.get('action',''),
            worker=request.form.get('worker',''))
        db.session.add(d); db.session.commit()
        flash('불량이 등록되었습니다.', 'success')
        return redirect(url_for('defect_list'))
    return render_template('defect_form.html', item=None, products=products,
                           molds=molds, results=results)

# ═══════════════════════════════════════════════
# 품질혁신 — 순회검사
# ═══════════════════════════════════════════════
@app.route('/inspection')
def insp_list():
    df = request.args.get('date', datetime.today().strftime('%Y-%m'))
    insps = Inspection.query.filter(
        Inspection.insp_date.like(f'{df}%')
    ).order_by(Inspection.id.desc()).all()
    total  = len(insps)
    passed = sum(1 for i in insps if i.overall_result == 'PASS')
    failed = total - passed
    pass_rate = round(passed / total * 100, 1) if total else 0
    return render_template('insp_list.html', insps=insps, date_filter=df,
                           total=total, passed=passed, failed=failed, pass_rate=pass_rate)

@app.route('/inspection/<int:iid>')
def insp_detail(iid):
    return render_template('insp_detail.html', insp=Inspection.query.get_or_404(iid))

@app.route('/inspection/new', methods=['GET','POST'])
def insp_new():
    products = Product.query.order_by(Product.code).all()
    molds    = Mold.query.filter_by(status='정상').order_by(Mold.code).all()
    if request.method == 'POST':
        insp_no = 'QI' + datetime.now().strftime('%Y%m%d%H%M%S')
        item_names = request.form.getlist('item_name')
        nominals   = request.form.getlist('nominal')
        usls       = request.form.getlist('usl')
        lsls       = request.form.getlist('lsl')
        measureds  = request.form.getlist('measured')
        items_list = []; overall = 'PASS'
        for i, name in enumerate(item_names):
            if not name.strip(): continue
            nom = _f(nominals[i]) if i < len(nominals) else None
            usl = _f(usls[i])     if i < len(usls)     else None
            lsl = _f(lsls[i])     if i < len(lsls)     else None
            msd = _f(measureds[i])if i < len(measureds) else None
            # ── 판정 로직 ──────────────────────────────────
            # 측정값 없으면 미검사(UNCHECKED) — PASS 판정 불가
            if msd is None:
                result = 'UNCHECKED'
                overall = 'FAIL'   # 미측정 항목 존재 시 전체 FAIL
            else:
                result = 'PASS'
                # USL/LSL 양측 동시 적용
                if usl is not None and lsl is not None:
                    if msd > usl or msd < lsl:
                        result = 'FAIL'
                elif usl is not None:
                    if msd > usl:
                        result = 'FAIL'
                elif lsl is not None:
                    if msd < lsl:
                        result = 'FAIL'
                if result == 'FAIL':
                    overall = 'FAIL'
            items_list.append(InspectionItem(item_name=name, nominal=nom,
                              usl=usl, lsl=lsl, measured=msd, result=result))
        insp = Inspection(
            insp_no=insp_no,
            insp_date=request.form.get('insp_date', datetime.today().strftime('%Y-%m-%d')),
            insp_time=request.form.get('insp_time',''),
            product_id=_i(request.form.get('product_id')),
            mold_id=_i(request.form.get('mold_id')),
            lot_no=request.form.get('lot_no',''),
            inspector=request.form.get('inspector','대표'),
            insp_type=request.form.get('insp_type','순회검사'),
            tool_used=request.form.get('tool_used','전자버니어캘리퍼스'),
            overall_result=overall,
            note=request.form.get('note',''),
            items=items_list)
        db.session.add(insp); db.session.commit()
        flash(f'검사 등록 완료. 결과: {overall}', 'success' if overall=='PASS' else 'danger')
        return redirect(url_for('insp_list'))
    return render_template('insp_form.html', item=None, products=products, molds=molds)

@app.route('/inspection/<int:iid>/delete', methods=['POST'])
def insp_delete(iid):
    db.session.delete(Inspection.query.get_or_404(iid))
    db.session.commit(); flash('삭제되었습니다.', 'warning')
    return redirect(url_for('insp_list'))

# ═══════════════════════════════════════════════
# 품질혁신 — 금형 기반 품질 트렌드 분석 (핵심 차별화)
# ═══════════════════════════════════════════════
@app.route('/quality/trend')
def quality_trend():
    # 30일 불량 추이
    trend = []
    for i in range(29, -1, -1):
        d  = (datetime.today() - timedelta(days=i)).strftime('%Y-%m-%d')
        ds = DefectRecord.query.filter_by(defect_date=d).all()
        trend.append({'date': d[-5:], 'count': sum(x.defect_qty for x in ds)})

    # 품목별 불량 TOP5
    prd_d = defaultdict(int)
    for d in DefectRecord.query.all():
        if d.product: prd_d[d.product.name] += d.defect_qty
    prd_top = sorted(prd_d.items(), key=lambda x: x[1], reverse=True)[:5]

    # 금형별 불량 TOP5
    mold_d = defaultdict(int)
    for d in DefectRecord.query.all():
        if d.mold: mold_d[d.mold.code] += d.defect_qty
    mold_top = sorted(mold_d.items(), key=lambda x: x[1], reverse=True)[:5]

    # 불량 유형별
    type_d = defaultdict(int)
    for d in DefectRecord.query.all():
        if d.defect_type: type_d[d.defect_type] += d.defect_qty
    type_top = sorted(type_d.items(), key=lambda x: x[1], reverse=True)[:8]

    # 금형 수명율 × 불량률 연계 데이터 (핵심 차별화 차트)
    mold_scatter = []
    for m in Mold.query.all():
        defects = DefectRecord.query.filter_by(mold_id=m.id).all()
        total_def = sum(d.defect_qty for d in defects)
        results   = [d.result for d in defects if d.result]
        total_prod= sum(r.total_qty for r in results) if results else 0
        dr = round(total_def / total_prod * 100, 3) if total_prod > 0 else 0
        mold_scatter.append({
            'label': m.code, 'x': m.life_rate, 'y': dr,
            'pm_alert': m.pm_alert
        })

    # LOT별 품질이력 (최근 20 LOT)
    lot_history = []
    results_q = ProductionResult.query.order_by(ProductionResult.id.desc()).limit(20).all()
    for r in results_q:
        dr = round(r.defect_qty / r.total_qty * 100, 2) if r.total_qty else 0
        mold_code = r.work_order.plan.mold.code if (r.work_order and r.work_order.plan and r.work_order.plan.mold) else '-'
        lot_history.append({
            'lot_no': r.lot_no, 'date': r.result_date,
            'total': r.total_qty, 'defect': r.defect_qty,
            'defect_rate': dr, 'mold': mold_code
        })

    return render_template('quality_trend.html',
        trend=trend, prd_top=prd_top, mold_top=mold_top,
        type_top=type_top, mold_scatter=mold_scatter, lot_history=lot_history)

# ═══════════════════════════════════════════════
# 유틸
# ═══════════════════════════════════════════════
def _f(v):
    try: return float(v) if v not in (None,'') else None
    except: return None

def _i(v):
    try: return int(v) if v not in (None,'') else None
    except: return None

def _mold_shot_quality(mold_id):
    """금형별 타수 구간 × 불량률 추이"""
    defects = DefectRecord.query.filter_by(mold_id=mold_id).all()
    data = []
    for d in defects:
        if d.result and d.result.total_qty > 0:
            dr = round(d.defect_qty / d.result.total_qty * 100, 2)
            data.append({'shot': d.result.work_order.plan.mold.current_shot if d.result.work_order and d.result.work_order.plan and d.result.work_order.plan.mold else 0,
                         'defect_rate': dr, 'date': d.defect_date})
    return data[:10]

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
