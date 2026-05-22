"""审批服务 — 消除三个业务模块审批逻辑的重复"""
from datetime import datetime

from app.models import ApprovalFlow


def get_approval_flow(user):
    """根据用户的部门获取适用的审批流程"""
    dept_name = user.department.name if user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    return flow


def get_required_role(user, current_step):
    """获取当前步骤需要的角色代码"""
    flow = get_approval_flow(user)
    if not flow:
        return None
    steps = flow.get_steps()
    if 1 <= current_step <= len(steps):
        return steps[current_step - 1].get('role_code')
    return None


def validate_approval(record, approver):
    """
    审批前置校验（通用逻辑）
    record: 实现了 status, current_step, user_id 属性的模型实例
    approver: User 对象
    returns: (ok: bool, error_msg: str)
    """
    # 状态检查
    if record.status == 'approved':
        return False, '该单据已审批完成'
    if record.status == 'rejected' and record.current_step > 1:
        return False, '该单据已被驳回，请等待申请人重新提交'
    # 自审检查
    if approver.id == record.user_id:
        return False, '不能审批自己的单据'
    # 步骤/权限检查
    flow = get_approval_flow(record.user)
    if not flow:
        return False, '未找到审批流程'
    steps = flow.get_steps()
    if record.current_step < 1 or record.current_step > len(steps):
        return False, '审批流程步骤异常'
    required_role = steps[record.current_step - 1].get('role_code')
    if approver.role != required_role:
        return False, f'您没有权限进行此步骤的审批，需要角色：{required_role}'
    return True, ''


def process_approval(record, action):
    """
    处理审批动作（通过/驳回）
    record: 实现了 status, current_step 属性的模型实例
    action: 'approve' 或 'reject'
    """
    flow = get_approval_flow(record.user)
    steps = flow.get_steps() if flow else []

    if action == 'approve':
        if record.current_step >= len(steps):
            record.status = 'approved'
        else:
            record.current_step += 1
            record.status = 'pending'
    elif action == 'reject':
        record.status = 'rejected'
        record.current_step = 1

    record.updated_at = datetime.now()


# ── 单据号生成 ──

def generate_number(prefix, model_cls):
    """生成前缀+9位数字的单据号，如 BXZF000000001"""
    last = model_cls.query.order_by(model_cls.id.desc()).first()
    if last:
        last_num = int(last.document_number.replace(prefix, ''))
        next_num = last_num + 1
    else:
        next_num = 1
    return f'{prefix}{str(next_num).zfill(9)}'
