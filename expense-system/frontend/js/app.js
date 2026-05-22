// ------------------------- 全局变量与工具函数 -------------------------
const API_URL = 'http://127.0.0.1:5000/api';
let currentPurchaseId = null;
let currentUser = null;
let currentClaimId = null;
let currentLoanId = null;
let allAccounts = [], allCurrencies = [], allExpenseTypes = [], allOperationTypes = [];
let availableLoans = [];  // 存储用户可用的借款单列表
let loanOffsetRows = [];  // 存储当前添加的冲账行数据（可选，用DOM管理也可以）

function getToken() { return localStorage.getItem('expense_token'); }
function setToken(t) { localStorage.setItem('expense_token', t); }
function clearToken() { localStorage.removeItem('expense_token'); }

async function fetchData(url) {
    const res = await fetch(`${API_URL}${url}`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
    if (res.status === 401) { clearToken(); showLogin(); throw new Error('未登录'); }
    if (!res.ok) { const err = await res.json(); throw new Error(err.error || '请求失败'); }
    return await res.json();
}
async function postData(url, data, files=null) {
    const fd = new FormData();
    for (let k in data) fd.append(k, data[k]);
    if (files) files.forEach(f => fd.append('receipts', f));
    const res = await fetch(`${API_URL}${url}`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` }, body: fd });
    if (res.status === 401) { clearToken(); showLogin(); throw new Error('未登录'); }
    if (!res.ok) throw new Error((await res.json()).error || '请求失败');
    return await res.json();
}
async function putData(url, data) {
    const res = await fetch(`${API_URL}${url}`, { method: 'PUT', headers: { 'Content-Type':'application/json', 'Authorization': `Bearer ${getToken()}` }, body: JSON.stringify(data) });
    if (!res.ok) throw new Error((await res.json()).error || '更新失败');
    return await res.json();
}
async function postJson(url, data) {
    const res = await fetch(`${API_URL}${url}`, { method: 'POST', headers: { 'Content-Type':'application/json', 'Authorization': `Bearer ${getToken()}` }, body: JSON.stringify(data) });
    if (!res.ok) throw new Error((await res.json()).error || '请求失败');
    return await res.json();
}
async function deleteData(url) {
    const res = await fetch(`${API_URL}${url}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${getToken()}` } });
    if (!res.ok) throw new Error((await res.json()).error || '删除失败');
    return await res.json();
}

function showLogin() { document.getElementById('login-page').style.display = 'flex'; document.getElementById('app-page').style.display = 'none'; }
function showApp() {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('app-page').style.display = 'block';
    if (currentUser) document.getElementById('current-user-name').innerText = `${currentUser.name} (${getRoleText(currentUser.role)})`;
    setupMenuByRole();
    loadInitialData();
    loadDepartmentsForSelect();
}
function getRoleText(role) {
    const map = { 'employee':'普通员工','department_manager':'部门主管','finance_staff':'财务会计','finance_manager':'财务经理','general_manager':'总经理','admin':'系统管理员' };
    return map[role] || role;
}
function setupMenuByRole() {
    const isAdmin = currentUser?.role === 'admin';
    const basicDataDiv = document.getElementById('menu-basic-data');
    const usersBtn = document.getElementById('menu-users');
    const flowsBtn = document.getElementById('menu-flows');
    const rolesBtn = document.getElementById('menu-roles');
    if (basicDataDiv) basicDataDiv.style.display = isAdmin ? 'block' : 'none';
    if (usersBtn) usersBtn.style.display = isAdmin ? 'block' : 'none';
    if (flowsBtn) flowsBtn.style.display = isAdmin ? 'block' : 'none';
    if (rolesBtn) rolesBtn.style.display = isAdmin ? 'block' : 'none';
}


// ------------------------- 初步数据加载 -------------------------
async function loadInitialData() {
    
    try { await loadClaims(); } catch(e) { console.error(e); }
    try { await loadPendingApprovals(); } catch(e) { console.error(e); }
}

async function editPurchase(id) {
    const purchase = await fetchData(`/purchases/${id}`);
    if (!purchase.is_draft) {
        viewPurchase(id);
        return;
    }
    // 直接显示面板，不触发 showPanel 里的 loadPurchaseFormData（无参数版会生成新单据号）
    document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
    document.getElementById('purchase_create-panel').style.display = 'block';
    await loadPurchaseFormData(id);
    const form = document.getElementById('purchase-form');
    window.originalPurchaseSubmit = form.onsubmit;
    form.onsubmit = async (e) => {
        e.preventDefault();
        await updatePurchaseDraft();
    };
}

async function editClaim(id) {
    const claim = await fetchData(`/claims/${id}`);
    if (!claim.is_draft) {
        viewClaim(id);
        return;
    }
    window.editingClaimId = id;
    // 直接显示面板，不触发 showPanel 里的 loadFormData
    document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
    document.getElementById('create-panel').style.display = 'block';
    // 等下拉数据加载完成
    await loadFormData();

    // 用草稿数据覆盖（loadFormData 生成的单据号会被覆盖）
    document.getElementById('claim-document-number').value = claim.document_number;
    document.getElementById('claim-user-name').value = `${claim.user_name} - ${claim.user_department || '无部门'} (${getRoleText(currentUser.role)})`;
    document.getElementById('claim-department').value = claim.department_id || '';
    document.getElementById('claim-legal-person').value = claim.legal_person_id || '';
    document.getElementById('claim-currency').value = claim.currency_id || '';
    document.getElementById('claim-description').value = claim.description || '';
    document.getElementById('claim-payee-account').value = claim.payee_account_id || '';
    document.getElementById('payee-amount').value = claim.amount;

    // 清空原有费用明细行
    const expenseTbody = document.getElementById('expense-items-body');
    expenseTbody.innerHTML = '';
    // 恢复费用明细
    if (claim.expense_items) {
        const items = JSON.parse(claim.expense_items);
        items.forEach(item => {
            addExpenseRowWithData(item.operationType, item.category, item.amount);
        });
    } else {
        addExpenseRow(); addExpenseRow();
    }

    // 清空冲账表格
    const offsetTbody = document.getElementById('loan-offset-tbody');
    offsetTbody.innerHTML = '';
    // 恢复冲账明细（如果有）
    if (claim.loan_details && claim.loan_details.length) {
        for (const ld of claim.loan_details) {
            addLoanOffsetRowWithLoanId(ld.loan_id, ld.amount);
        }
    } else {
        addLoanOffsetRow();  // 如果没有冲账，就加一个空行
    }

    // 显示草稿已有的附件
    const uploadedDiv = document.getElementById('uploaded-files');
    if (claim.receipts && claim.receipts.length) {
        let html = '';
        claim.receipts.forEach((r, i) => {
            html += `<div class="badge" data-receipt-id="${r.id}">${i+1}. ${r.original_name} <button type="button" class="btn btn-danger btn-sm" onclick="removeReceiptFromDraft(${r.id}, this)">删除</button></div>`;
        });
        uploadedDiv.innerHTML = html;
    } else {
        uploadedDiv.innerHTML = '';
    }

    // 修改表单提交行为，使其更新草稿而不是新建
    const form = document.getElementById('claim-form');
    window.originalClaimSubmit = form.onsubmit;
    form.onsubmit = async (e) => {
        e.preventDefault();
        await updateClaimDraft();
    };
}
// 删除草稿中的附件
async function removeReceiptFromDraft(receiptId, btn) {
    if (!confirm('确定删除此附件吗？删除后不可恢复。')) return;
    try {
        await deleteData(`/receipts/${receiptId}`);
        btn.parentElement.remove();
        showToast('附件删除成功', 'success');
    } catch(e) {
        showToast(e.message, 'error');
    }
}    
async function editLoan(id) {
    const loan = await fetchData(`/loans/${id}`);
    if (!loan.is_draft) {
        viewLoan(id);
        return;
    }
    // 直接显示面板，不触发 showPanel 里的 loadLoanFormData（无参数版会生成新单据号）
    document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
    document.getElementById('loan_create-panel').style.display = 'block';
    // 传入草稿ID加载数据
    await loadLoanFormData(id);
    // 修改表单提交行为，使其更新草稿而不是新建
    const form = document.getElementById('loan-form');
    window.originalLoanSubmit = form.onsubmit;
    form.onsubmit = async (e) => {
        e.preventDefault();
        await updateLoanDraft();
    };
}
// 添加冲账行并自动选中某个借款单，用于编辑草稿时恢复
function addLoanOffsetRowWithLoanId(loanId, offsetAmount) {
    const tbody = document.getElementById('loan-offset-tbody');
    const rowId = Date.now() + Math.random();
    const row = document.createElement('tr');
    row.setAttribute('data-row-id', rowId);
    
    let loanOptions = '<option value="">请选择借款单</option>';
    availableLoans.forEach(loan => {
        loanOptions += `<option value="${loan.id}" data-total="${loan.total_amount}" data-reimbursed="${loan.total_reimbursed}" data-remaining="${loan.remaining}">${loan.document_number} (剩余可核销: ${loan.remaining.toFixed(2)})</option>`;
    });
    
    row.innerHTML = `
        <td><select class="loan-select" onchange="updateLoanInfo(this)">${loanOptions}</select></td>
        <td><input type="text" class="loan-total" readonly style="background:#f8f9fa;" value=""></td>
        <td><input type="text" class="loan-reimbursed" readonly style="background:#f8f9fa;" value=""></td>
        <td><input type="text" class="loan-remaining" readonly style="background:#f8f9fa;" value=""></td>
        <td><input type="number" class="offset-amount" step="0.01" value="${offsetAmount}" oninput="calculateTotalOffset()"></td>
        <td><button type="button" class="btn btn-danger btn-sm" onclick="removeLoanOffsetRow(this)">删除</button></td>
    `;
    tbody.appendChild(row);
    
    // 选中对应的借款单
    const select = row.querySelector('.loan-select');
    select.value = loanId;
    updateLoanInfo(select);
    calculateTotalOffset();
}

// 辅助函数：带数据添加费用明细行
function addExpenseRowWithData(operationType, category, amount) {
    const tbody = document.getElementById('expense-items-body');
    const idx = tbody.children.length + 1;
    const opOpts = allOperationTypes.length ? allOperationTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="销售业务">销售业务</option>';
    const catOpts = allExpenseTypes.length ? allExpenseTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="差旅费">差旅费</option>';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${idx}</td><td><select class="operation-type" required>${opOpts}</select></td><td><select class="expense-category" required>${catOpts}</select></td><td><input type="number" class="expense-amount" step="0.01" required value="${amount}" oninput="updatePayeeAmountWithOffset()"></td><td><button type="button" class="btn btn-danger btn-sm" onclick="removeExpenseRow(this)">删除</button></td>`;
    tbody.appendChild(tr);
    if (operationType) tr.querySelector('.operation-type').value = operationType;
    if (category) tr.querySelector('.expense-category').value = category;
}

async function updateClaimDraft() {
    // 收集费用明细
    const expenseItems = [];
    document.querySelectorAll('#expense-items-body tr').forEach(row => {
        const operationType = row.querySelector('.operation-type').value;
        const category = row.querySelector('.expense-category').value;
        const amount = parseFloat(row.querySelector('.expense-amount').value) || 0;
        expenseItems.push({ operationType, category, amount });
    });
    const expenseItemsJson = JSON.stringify(expenseItems);
    
    // 计算报销总额
    let total = 0;
    expenseItems.forEach(item => total += item.amount);
    
    // 收集冲账明细
    const loanDetails = [];
    document.querySelectorAll('#loan-offset-tbody tr').forEach(row => {
        const loanSelect = row.querySelector('.loan-select');
        const offsetInput = row.querySelector('.offset-amount');
        if (loanSelect && loanSelect.value && parseFloat(offsetInput.value) > 0) {
            loanDetails.push({
                loan_id: parseInt(loanSelect.value),
                amount: parseFloat(offsetInput.value)
            });
        }
    });
    const loanDetailsJson = JSON.stringify(loanDetails);
    
    if (!currentUser || !currentUser.id) { alert('未登录'); return; }
    const data = {
        user_id: currentUser.id,
        department_id: document.getElementById('claim-department').value || '',
        legal_person_id: document.getElementById('claim-legal-person').value || '',
        currency_id: document.getElementById('claim-currency').value,
        payee_account_id: document.getElementById('claim-payee-account').value || '',
        amount: total,
        category: expenseItems[0]?.category || '其他',
        description: document.getElementById('claim-description').value,
        loan_details: loanDetailsJson,
        expense_items: expenseItemsJson
    };
    try {
        const res = await putData(`/claims/draft/${window.editingClaimId}`, data);
        alert(res.message);
        delete window.editingClaimId;
        // 恢复表单默认提交行为
        document.getElementById('claim-form').onsubmit = window.originalClaimSubmit;
        showPanel('claims');
        loadClaims();
    } catch(err) { alert('更新失败: '+err.message); }
}

// ------------------------- 报销单据相关 -------------------------
async function loadClaims() {
    try {
        const params = new URLSearchParams();
        const role = currentUser?.role;
        if (role && !['admin'].includes(role)) params.append('view_mode', 'my');
        const claims = await fetchData(`/claims?${params}`);
        const tbody = document.getElementById('claims-table-body');
        tbody.innerHTML = claims.length ? claims.map(c => {
            const isDraft = c.is_draft;
            const statusText = isDraft ? '草稿' : getStatusText(c.status);
            const statusClass = isDraft ? 'draft' : c.status;
            const showDelete = (!isDraft && c.status==='pending' && c.user_id===currentUser?.id && c.current_step===1 && (!c.approvals || c.approvals.length===0));
            return `
            <tr>
                <td>${c.document_number}</td>
                <td>${c.user_name}</td>
                <td>${c.user_department||'-'}</td>
                <td>${c.legal_person_name||'-'}</td>
                <td>${c.currency_symbol||'¥'}${c.amount.toFixed(2)}</td>
                <td>${c.payee_account_name||'-'}</td>
                <td>${c.category}</td>
                <td><span class="status ${statusClass}">${statusText}</span></td>
                <td>${formatDate(c.created_at)}</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="${isDraft ? `editClaim(${c.id})` : `viewClaim(${c.id})`}">${isDraft ? '编辑' : '查看'}</button>
                    ${showDelete ? `<button class="btn btn-danger btn-sm" onclick="deleteClaim(${c.id})">删除</button>` : ''}
                </td>
            </tr>
        `}).join('') : '<tr><td colspan="10" class="empty-state">暂无报销单据</td></tr>';
    } catch(e) { console.error(e); document.getElementById('claims-table-body').innerHTML = '<tr><td colspan="10" class="empty-state">加载失败</td></tr>'; }
}
function getStatusText(status) { return { pending:'待审批', approved:'已通过', rejected:'已拒绝' }[status] || status; }
function formatDate(d) { return new Date(d).toLocaleString('zh-CN'); }
async function viewClaim(id) {
    const claim = await fetchData(`/claims/${id}`);
    currentClaimId = id;
    const isApprover = canApproveClaim(claim);
    const isOwner = claim.user_id === currentUser?.id;
    document.getElementById('approval-detail').innerHTML = `
        <div class="approval-info">
            <div class="info-row">
                <span class="info-label">单据号</span>
                <span class="info-value doc-number">${claim.document_number}</span>
            </div>
            <div class="info-row">
                <span class="info-label">申请人</span>
                <span class="info-value">${claim.user_name} (${claim.user_department||'-'})</span>
            </div>
            <div class="info-row">
                <span class="info-label">法人主体</span>
                <span class="info-value">${claim.legal_person_name||'-'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">币种</span>
                <span class="info-value">${claim.currency_code||'CNY'}</span>
            </div>
            <div class="info-row highlight">
                <span class="info-label">报销总额</span>
                <span class="info-value amount">${claim.currency_symbol||'¥'}${claim.amount.toFixed(2)}</span>
            </div>
            ${claim.loan_details && claim.loan_details.length ? `
            <div class="info-row">
                <span class="info-label">借款冲账明细</span>
                <div class="info-value">
                    <table style="width:100%; border-collapse:collapse; margin-top:5px;">
                        <thead>
                            <tr><th>借款单据号</th><th>本次冲账金额</th><th>冲账后剩余可核销</th>
                        </thead>
                        <tbody>
                            ${claim.loan_details.map(ld => `
                                <tr>
                                    <td>${ld.document_number}</td>
                                    <td>${claim.currency_symbol||'¥'}${ld.offset_amount.toFixed(2)}</td>
                                    <td>${claim.currency_symbol||'¥'}${ld.remaining_after_offset.toFixed(2)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                    <div style="margin-top:8px;"><strong>本次冲账合计：</strong> ${claim.currency_symbol||'¥'}${claim.total_offset.toFixed(2)}</div>
                </div>
            </div>
            <div class="info-row highlight">
                <span class="info-label">本次实际收款</span>
                <span class="info-value amount">${claim.currency_symbol||'¥'}${claim.actual_payee_amount.toFixed(2)}</span>
            </div>
            ` : ''}
            <div class="info-row">
                <span class="info-label">收款账户</span>
                <span class="info-value">${claim.payee_account_name||'-'} (${claim.payee_account_number||'-'})</span>
            </div>
            <div class="info-row">
                <span class="info-label">类别</span>
                <span class="info-value">${claim.category}</span>
            </div>
            <div class="info-row">
                <span class="info-label">说明</span>
                <span class="info-value">${claim.description||'-'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">创建时间</span>
                <span class="info-value">${formatDate(claim.created_at)}</span>
            </div>
            <div class="info-row status-row">
                <span class="info-label">当前状态</span>
                <span class="info-value"><span class="status ${claim.status}">${getStatusText(claim.status)}</span> (第${claim.current_step}步)</span>
            </div>
            ${claim.receipts.length ? `
            <div class="info-row">
                <span class="info-label">票据</span>
                <span class="info-value">${claim.receipts.map(r => `<a href="${API_URL.replace('/api','')}/uploads/${r.filename}" target="_blank" class="receipt-link">${r.original_name}</a>`).join(', ')}</span>
            </div>` : ''}
            ${claim.approvals.length ? `
            <div class="approval-history">
                <div class="history-title">审批记录</div>
                <div class="history-list">
                    ${claim.approvals.map((a, idx) => `
                    <div class="history-item">
                        <div class="history-step">${a.step}</div>
                        <div class="history-content">
                            <span class="history-name">${a.approver_name}</span>
                            <span class="history-action ${a.action}">${a.action==='approve'?'✓ 通过':'✗ 拒绝'}</span>
                            ${a.comment ? `<span class="history-comment">(${a.comment})</span>` : ''}
                        </div>
                    </div>`).join('')}
                </div>
            </div>` : ''}
        </div>
    `;
    const actionsDiv = document.getElementById('approval-actions');
    if (isApprover) {
        actionsDiv.style.display = 'flex';
        actionsDiv.innerHTML = `<button class="btn btn-success" onclick="submitApproval('approve')">审批通过</button><button class="btn btn-danger" onclick="submitApproval('reject')">驳回申请</button><input type="text" id="approval-comment" placeholder="审批意见（可选）" style="flex:1;">`;
    } else actionsDiv.style.display = 'none';
    document.getElementById('reedit-actions').style.display = (claim.status==='rejected' && isOwner) ? 'flex' : 'none';
    document.getElementById('approval-modal').classList.add('show');
}
async function viewApprovalClaim(id) { await viewClaim(id); }
function canApproveClaim(claim) {
    if (claim.status !== 'pending') return false;
    if (claim.user_id === currentUser?.id) return false;
    return claim.required_role === currentUser?.role;
}
async function submitApproval(action) {
    const comment = document.getElementById('approval-comment')?.value || '';
    try {
        const res = await fetch(`${API_URL}/approvals/${currentClaimId}`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type':'application/json' },
            body: JSON.stringify({ action, comment })
        });
        if (!res.ok) throw new Error((await res.json()).error);
        showToast((await res.json()).message, 'success');
        document.getElementById('approval-modal').classList.remove('show');
        loadClaims(); loadPendingApprovals();
    } catch(e) { showToast(e.message, 'error'); }
}
function closeApprovalModal() { document.getElementById('approval-modal').classList.remove('show'); }
async function deleteClaim(id) {
    if (!confirm('确定删除此报销单吗？删除后不可恢复。')) return;
    try {
        const res = await deleteData(`/claims/${id}`);
        showToast(res.message || '删除成功', 'success');
        loadClaims();  // 刷新列表
    } catch(err) {
        showToast(err.message || '删除失败', 'error');
    }
}

async function loadPendingApprovals() {
    try {
        const claims = await fetchData('/claims?view_mode=pending_approval');
        const tbody = document.getElementById('approvals-table-body');
        tbody.innerHTML = claims.length ? claims.map(c => `
            <tr><td>${c.document_number}</td><td>${c.user_name}</td><td>${c.user_department||'-'}</td><td>${c.legal_person_name||'-'}</td><td>${c.currency_symbol||'¥'}${c.amount.toFixed(2)}</td><td>${c.category}</td><td><span class="status ${c.status}">${getStatusText(c.status)}</span></td><td>${formatDate(c.created_at)}</td><td><button class="btn btn-primary btn-sm" onclick="viewApprovalClaim(${c.id})">审批</button></td></tr>
        `).join('') : '<tr><td colspan="9" class="empty-state">暂无待审批单据</td></tr>';
    } catch(e) { console.error(e); }
}
async function loadApprovals() {
    const isPending = document.querySelector('#approvals-panel .nav-tabs .active')?.innerText === '待我审批';
    const url = isPending ? '/claims?view_mode=pending_approval' : '/claims?view_mode=all';
    const claims = await fetchData(url);
    const tbody = document.getElementById('approvals-table-body');
    tbody.innerHTML = claims.length ? claims.map(c => `
        <tr><td>${c.document_number}</td><td>${c.user_name}</td><td>${c.user_department||'-'}</td><td>${c.legal_person_name||'-'}</td><td>${c.currency_symbol||'¥'}${c.amount.toFixed(2)}</td><td>${c.category}</td><td><span class="status ${c.status}">${getStatusText(c.status)}</span></td><td>${formatDate(c.created_at)}</td><td><button class="btn btn-secondary btn-sm" onclick="viewClaim(${c.id})">查看</button>${isPending?`<button class="btn btn-primary btn-sm" onclick="viewApprovalClaim(${c.id})">审批</button>`:''}</td></tr>
    `).join('') : '<tr><td colspan="9" class="empty-state">暂无数据</td></tr>';
}
function filterApprovals(filter) {
    document.querySelectorAll('#approvals-panel .nav-tabs button').forEach(b=>b.classList.remove('active'));
    event.target.classList.add('active');
    loadApprovals();
}

// ------------------------- 报销申请表单 -------------------------
async function loadFormData() {
    try {
        // 不再加载用户列表，因为申请人固定为当前登录用户
        const depts = await fetchData('/departments');
        const persons = await fetchData('/legal_persons');
        const currencies = await fetchData('/currencies');
        const accounts = await fetchData('/payee_accounts');
        const expenseTypes = await fetchData('/expense_types');
        const operationTypes = await fetchData('/operation_types');
        const docNum = await fetchData('/next_document_number');
        allAccounts = accounts; allCurrencies = currencies; allExpenseTypes = expenseTypes; allOperationTypes = operationTypes;
        document.getElementById('claim-document-number').value = docNum.document_number;
        
        // 设置申请人只读字段，显示当前用户信息
        const userNameField = document.getElementById('claim-user-name');
        if (userNameField && currentUser) {
            userNameField.value = `${currentUser.name} - ${currentUser.department || '无部门'} (${getRoleText(currentUser.role)})`;
        }
        // 部门下拉：默认选中当前用户的部门
        const deptSelect = document.getElementById('claim-department');
        deptSelect.innerHTML = '<option value="">请选择部门</option>' + depts.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
        if (currentUser && currentUser.department_id) {
            deptSelect.value = currentUser.department_id;
        }
        
        // 法人、币种、收款账户等保持不变...
        document.getElementById('claim-legal-person').innerHTML = '<option value="">请选择法人主体</option>' + persons.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
        document.getElementById('claim-currency').innerHTML = currencies.map(c => `<option value="${c.id}">${c.code} - ${c.name}</option>`).join('');
        document.getElementById('claim-payee-account').innerHTML = '<option value="">请选择收款账户</option>' + accounts.map(a => `<option value="${a.id}">${a.account_name} - ${a.bank_short_name||''}</option>`).join('');
        const catOpts = expenseTypes.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
        document.querySelectorAll('.expense-category').forEach(sel => sel.innerHTML = catOpts);
        const opOpts = operationTypes.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
        document.querySelectorAll('.operation-type').forEach(sel => sel.innerHTML = opOpts);
        await loadAvailableLoans();                     // 加载可用借款单
const offsetTbody = document.getElementById('loan-offset-tbody');
if (offsetTbody) offsetTbody.innerHTML = '';    // 清空旧行
addLoanOffsetRow();                             // 添加一行空白冲账行
        updatePayeeAmountWithOffset();
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        const dateInput = document.getElementById('claim-date');
        if (dateInput) dateInput.value = `${yyyy}-${mm}-${dd}`;
    } catch(e) { console.error(e); }
}
function addExpenseRow() {
    const tbody = document.getElementById('expense-items-body');
    const idx = tbody.children.length + 1;
    const opOpts = allOperationTypes.length ? allOperationTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="销售业务">销售业务</option>';
    const catOpts = allExpenseTypes.length ? allExpenseTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="差旅费">差旅费</option>';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${idx}</td><td><select class="operation-type" required>${opOpts}</select></td><td><select class="expense-category" required>${catOpts}</select></td><td><input type="number" class="expense-amount" step="0.01" required oninput="updatePayeeAmountWithOffset()"></td><td><button type="button" class="btn btn-danger btn-sm" onclick="removeExpenseRow(this)">删除</button></td>`;
    tbody.appendChild(tr);
    updatePayeeAmountWithOffset()
}
function removeExpenseRow(btn) {
    const tbody = document.getElementById('expense-items-body');
    if (tbody.children.length > 1) {
        btn.closest('tr').remove();
        Array.from(tbody.children).forEach((row,i)=>row.cells[0].innerText = i+1);
        updatePayeeAmountWithOffset()
    }
}
function updatePayeeAmount() {
    let total = 0;
    document.querySelectorAll('.expense-amount').forEach(inp => { if(inp.value) total += parseFloat(inp.value); });
    const currency = allCurrencies.find(c => c.id == document.getElementById('claim-currency').value);
    const symbol = currency?.symbol || '¥';
    document.getElementById('total-amount').innerHTML = `${symbol}${total.toFixed(2)}`;
    const payeeAmt = document.getElementById('payee-amount');
    if (!payeeAmt.value || payeeAmt.dataset.auto==='true') { payeeAmt.value = total.toFixed(2); payeeAmt.dataset.auto = 'true'; }
}
document.getElementById('claim-currency')?.addEventListener('change', updatePayeeAmountWithOffset);
document.getElementById('claim-payee-account')?.addEventListener('change', function() {
    const acc = allAccounts.find(a => a.id == this.value);
    document.getElementById('payee-name').value = acc?.account_name || '';
    document.getElementById('payee-number').value = acc?.account_number || '';
});
document.getElementById('claim-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const rows = document.querySelectorAll('#expense-items-body tr');
    let total = 0, mainCat = '';
    rows.forEach(row => { 
        const amt = parseFloat(row.querySelector('.expense-amount').value) || 0; 
        total += amt; 
        if (!mainCat) mainCat = row.querySelector('.expense-category').value; 
    });
    if (total <= 0) { 
        alert('请输入报销金额'); 
        return; 
    }
    if (!currentUser || !currentUser.id) { 
        alert('未登录，请重新登录'); 
        return; 
    }
    const userId = currentUser.id;

// 收集冲账明细
const loanDetails = [];
document.querySelectorAll('#loan-offset-tbody tr').forEach(row => {
    const loanSelect = row.querySelector('.loan-select');
    const offsetInput = row.querySelector('.offset-amount');
    if (loanSelect && loanSelect.value && parseFloat(offsetInput.value) > 0) {
        loanDetails.push({
            loan_id: parseInt(loanSelect.value),
            amount: parseFloat(offsetInput.value)
        });
    }
});
const loanDetailsJson = JSON.stringify(loanDetails);
    
    const data = {
        user_id: userId,
        department_id: document.getElementById('claim-department').value || '',
        legal_person_id: document.getElementById('claim-legal-person').value || '',
        currency_id: document.getElementById('claim-currency').value,
        payee_account_id: document.getElementById('claim-payee-account').value || '',
        amount: total,
        category: mainCat,
        description: document.getElementById('claim-description').value,
        loan_details: loanDetailsJson
    };

    const files = Array.from(document.getElementById('receipt-files').files);
    try {
        const res = await postData('/claims', data, files);
        alert(`报销单创建成功！单据号: ${res.document_number}`);
        document.getElementById('claim-form').reset();
        // 重置冲账表格
        const offsetTbody = document.getElementById('loan-offset-tbody');
        if (offsetTbody) offsetTbody.innerHTML = '';
        addLoanOffsetRow();
        loadFormData();
    } catch(err) { 
        alert('提交失败: ' + err.message); 
    }
});
document.getElementById('upload-area')?.addEventListener('click', () => document.getElementById('receipt-files').click());
document.getElementById('receipt-files')?.addEventListener('change', (e) => {
    const files = Array.from(e.target.files);
    document.getElementById('uploaded-files').innerHTML = files.map((f,i)=>`<div class="badge">${i+1}. ${f.name}</div>`).join('');
});

async function loadAvailableLoans() {
    try {
        availableLoans = await fetchData('/user_available_loans');
    } catch(e) {
        console.error('加载可用借款单失败', e);
        availableLoans = [];
    }
}

function addLoanOffsetRow(selectedLoanId = null) {
    const tbody = document.getElementById('loan-offset-tbody');
    const rowId = Date.now() + Math.random();
    const row = document.createElement('tr');
    row.setAttribute('data-row-id', rowId);
    
    // 借款单下拉框
    let loanOptions = '<option value="">请选择借款单</option>';
    availableLoans.forEach(loan => {
        loanOptions += `<option value="${loan.id}" data-total="${loan.total_amount}" data-reimbursed="${loan.total_reimbursed}" data-remaining="${loan.remaining}">${loan.document_number} (剩余可核销: ${loan.remaining.toFixed(2)})</option>`;
    });
    
    row.innerHTML = `
        <td><select class="loan-select" onchange="updateLoanInfo(this)">${loanOptions}</select></td>
        <td><input type="text" class="loan-total" readonly style="background:#f8f9fa;" value=""></td>
        <td><input type="text" class="loan-reimbursed" readonly style="background:#f8f9fa;" value=""></td>
        <td><input type="text" class="loan-remaining" readonly style="background:#f8f9fa;" value=""></td>
        <td><input type="number" class="offset-amount" step="0.01" value="0" oninput="calculateTotalOffset()"></td>
        <td><button type="button" class="btn btn-danger btn-sm" onclick="removeLoanOffsetRow(this)">删除</button></td>
    `;
    tbody.appendChild(row);
    
    if (selectedLoanId) {
        const select = row.querySelector('.loan-select');
        select.value = selectedLoanId;
        updateLoanInfo(select);
    }
    calculateTotalOffset();
}

function updateLoanInfo(selectElement) {
    const row = selectElement.closest('tr');
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    if (selectElement.value) {
        const total = parseFloat(selectedOption.getAttribute('data-total'));
        const reimbursed = parseFloat(selectedOption.getAttribute('data-reimbursed'));
        const remaining = parseFloat(selectedOption.getAttribute('data-remaining'));
        row.querySelector('.loan-total').value = total.toFixed(2);
        row.querySelector('.loan-reimbursed').value = reimbursed.toFixed(2);
        row.querySelector('.loan-remaining').value = remaining.toFixed(2);
        // 限制本次核销金额不能超过 remaining
        const offsetInput = row.querySelector('.offset-amount');
        offsetInput.max = remaining;
        if (parseFloat(offsetInput.value) > remaining) offsetInput.value = remaining;
    } else {
        row.querySelector('.loan-total').value = '';
        row.querySelector('.loan-reimbursed').value = '';
        row.querySelector('.loan-remaining').value = '';
        row.querySelector('.offset-amount').value = 0;
    }
    calculateTotalOffset();
}

function removeLoanOffsetRow(btn) {
    const row = btn.closest('tr');
    row.remove();
    calculateTotalOffset();
}

function calculateTotalOffset() {
    let totalOffset = 0;
    document.querySelectorAll('#loan-offset-tbody .offset-amount').forEach(inp => {
        let val = parseFloat(inp.value) || 0;
        totalOffset += val;
    });
    const symbol = getCurrentCurrencySymbol(); // 获取当前币种符号，可复用
    document.getElementById('total-offset-amount').innerHTML = `${symbol}${totalOffset.toFixed(2)}`;
    
    // 更新收款金额（报销合计 - 冲账合计）
    updatePayeeAmountWithOffset();
}

function getCurrentCurrencySymbol() {
    const currencySelect = document.getElementById('claim-currency');
    if (currencySelect && currencySelect.value) {
        const currency = allCurrencies.find(c => c.id == currencySelect.value);
        return currency?.symbol || '¥';
    }
    return '¥';
}

// 修改原来的 updatePayeeAmount 函数，增加冲账合计的影响
function updatePayeeAmountWithOffset() {
    // 计算报销费用合计
    let expenseTotal = 0;
    document.querySelectorAll('.expense-amount').forEach(inp => {
        if(inp.value) expenseTotal += parseFloat(inp.value);
    });
    // 计算冲账合计
    let offsetTotal = 0;
    document.querySelectorAll('#loan-offset-tbody .offset-amount').forEach(inp => {
        if(inp.value) offsetTotal += parseFloat(inp.value);
    });
    const finalAmount = expenseTotal - offsetTotal;
    const symbol = getCurrentCurrencySymbol();
    document.getElementById('total-amount').innerHTML = `${symbol}${expenseTotal.toFixed(2)}`;
    // 更新收款金额字段（payee-amount）
    const payeeAmt = document.getElementById('payee-amount');
    if (payeeAmt) {
        payeeAmt.value = finalAmount.toFixed(2);
        payeeAmt.dataset.auto = 'true';
    }
    // 同时更新冲账合计显示
    document.getElementById('total-offset-amount').innerHTML = `${symbol}${offsetTotal.toFixed(2)}`;
}

// 借款表单数据
async function loadLoanFormData(draftId = null) {
    try {
        const depts = await fetchData('/departments');
        const persons = await fetchData('/legal_persons');
        const currencies = await fetchData('/currencies');
        const accounts = await fetchData('/payee_accounts');
        const expenseTypes = await fetchData('/expense_types');
        const operationTypes = await fetchData('/operation_types');
        
        // 如果是编辑草稿，需要获取草稿详情
        let loanData = null;
        if (draftId) {
            loanData = await fetchData(`/loans/${draftId}`);
            window.editingLoanId = draftId;
        } else {
            window.editingLoanId = null;
            const docNum = await fetchData('/next_loan_number');
            document.getElementById('loan-document-number').value = docNum.document_number;
        }
        
        window.loanAccounts = accounts;
        window.loanCurrencies = currencies;
        window.loanExpenseTypes = expenseTypes;
        window.loanOperationTypes = operationTypes;
        
        // 设置申请人等
        const userNameField = document.getElementById('loan-user-name');
        if (userNameField && currentUser) {
            userNameField.value = `${currentUser.name} - ${currentUser.department || '无部门'} (${getRoleText(currentUser.role)})`;
        }
        
        const deptSelect = document.getElementById('loan-department');
        deptSelect.innerHTML = '<option value="">请选择部门</option>' + depts.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
        if (loanData) {
            if (loanData.department_id) deptSelect.value = loanData.department_id;
            document.getElementById('loan-legal-person').value = loanData.legal_person_id || '';
            document.getElementById('loan-currency').value = loanData.currency_id || '';
            document.getElementById('loan-payee-account').value = loanData.payee_account_id || '';
            document.getElementById('loan-purpose').value = loanData.purpose || '';
            document.getElementById('loan-document-number').value = loanData.document_number;
            // 恢复借款明细表格
            const tbody = document.getElementById('loan-expense-items-body');
            tbody.innerHTML = '';
            let items = [];
            if (loanData.loan_items) {
                items = JSON.parse(loanData.loan_items);
            }
            if (items.length === 0) {
                addLoanExpenseRow(); addLoanExpenseRow();
            } else {
                items.forEach(item => {
                    addLoanExpenseRowWithData(item.operationType, item.category, item.amount);
                });
            }
            // 恢复收款金额
            document.getElementById('loan-payee-amount').value = loanData.amount;
        } else {
            // 新建模式，使用默认值
            const docNum = await fetchData('/next_loan_number');
            document.getElementById('loan-document-number').value = docNum.document_number;
            if (currentUser && currentUser.department_id) deptSelect.value = currentUser.department_id;
            document.getElementById('loan-legal-person').innerHTML = '<option value="">请选择法人主体</option>' + persons.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
            document.getElementById('loan-currency').innerHTML = currencies.map(c => `<option value="${c.id}">${c.code} - ${c.name}</option>`).join('');
            document.getElementById('loan-payee-account').innerHTML = '<option value="">请选择收款账户</option>' + accounts.map(a => `<option value="${a.id}">${a.account_name} - ${a.bank_short_name||''}</option>`).join('');
            // 清空借款明细，添加两行空行
            const tbody = document.getElementById('loan-expense-items-body');
            tbody.innerHTML = '';
            addLoanExpenseRow(); addLoanExpenseRow();
        }
        
        // 设置日期
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        document.getElementById('loan-date').value = `${yyyy}-${mm}-${dd}`;
        
        updateLoanPayeeAmount();
    } catch(e) { console.error(e); }
}

function addLoanExpenseRow() {
    const tbody = document.getElementById('loan-expense-items-body');
    const idx = tbody.children.length + 1;
    const opOpts = (window.loanOperationTypes || []).length ? window.loanOperationTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="销售业务">销售业务</option>';
    const catOpts = (window.loanExpenseTypes || []).length ? window.loanExpenseTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="差旅费">差旅费</option>';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${idx}</td><td><select class="loan-operation-type" required>${opOpts}</select></td><td><select class="loan-category" required>${catOpts}</select></td><td><input type="number" class="loan-amount" step="0.01" required oninput="updateLoanPayeeAmount()"></td><td><button type="button" class="btn btn-danger btn-sm" onclick="removeLoanExpenseRow(this)">删除</button></td>`;
    tbody.appendChild(tr);
    updateLoanPayeeAmount();
}

function addLoanExpenseRowWithData(operationType, category, amount) {
    const tbody = document.getElementById('loan-expense-items-body');
    const idx = tbody.children.length + 1;
    const opOpts = (window.loanOperationTypes || []).length ? window.loanOperationTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="销售业务">销售业务</option>';
    const catOpts = (window.loanExpenseTypes || []).length ? window.loanExpenseTypes.map(t=>`<option value="${t.name}">${t.name}</option>`).join('') : '<option value="差旅费">差旅费</option>';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${idx}</td><td><select class="loan-operation-type" required>${opOpts}</select></td><td><select class="loan-category" required>${catOpts}</select></td><td><input type="number" class="loan-amount" step="0.01" required value="${amount}" oninput="updateLoanPayeeAmount()"></td><td><button type="button" class="btn btn-danger btn-sm" onclick="removeLoanExpenseRow(this)">删除</button></td>`;
    tbody.appendChild(tr);
    if (operationType) tr.querySelector('.loan-operation-type').value = operationType;
    if (category) tr.querySelector('.loan-category').value = category;
}

function removeLoanExpenseRow(btn) {
    const tbody = document.getElementById('loan-expense-items-body');
    if (tbody.children.length > 1) {
        btn.closest('tr').remove();
        Array.from(tbody.children).forEach((row,i)=>row.cells[0].innerText = i+1);
        updateLoanPayeeAmount();
    }
}
function updateLoanPayeeAmount() {
    let total = 0;
    document.querySelectorAll('.loan-amount').forEach(inp => { if(inp.value) total += parseFloat(inp.value); });
    const currency = (window.loanCurrencies || []).find(c => c.id == document.getElementById('loan-currency').value);
    const symbol = currency?.symbol || '¥';
    document.getElementById('loan-total-amount').innerHTML = `${symbol}${total.toFixed(2)}`;
    const payeeAmt = document.getElementById('loan-payee-amount');
    if (!payeeAmt.value || payeeAmt.dataset.auto==='true') { payeeAmt.value = total.toFixed(2); payeeAmt.dataset.auto = 'true'; }
}
document.getElementById('loan-currency')?.addEventListener('change', updateLoanPayeeAmount);
document.getElementById('loan-payee-account')?.addEventListener('change', function() {
    const acc = (window.loanAccounts || []).find(a => a.id == this.value);
    document.getElementById('loan-payee-name').value = acc?.account_name || '';
    document.getElementById('loan-payee-number').value = acc?.account_number || '';
});
document.getElementById('loan-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const rows = document.querySelectorAll('#loan-expense-items-body tr');
    let total = 0, mainCat = '';
    const loanItems = [];
    rows.forEach(row => {
        const operationType = row.querySelector('.loan-operation-type').value;
        const category = row.querySelector('.loan-category').value;
        const amt = parseFloat(row.querySelector('.loan-amount').value) || 0;
        total += amt;
        if(!mainCat) mainCat = category;
        loanItems.push({ operationType, category, amount: amt });
    });
    const loanItemsJson = JSON.stringify(loanItems);
    if(total <= 0) { alert('请输入借款金额'); return; }
    if (!currentUser || !currentUser.id) { alert('未登录，请重新登录'); return; }
    const userId = currentUser.id;
    const data = {
        user_id: userId,
        department_id: document.getElementById('loan-department').value || '',
        legal_person_id: document.getElementById('loan-legal-person').value || '',
        currency_id: document.getElementById('loan-currency').value,
        payee_account_id: document.getElementById('loan-payee-account').value || '',
        amount: total, category: mainCat,
        purpose: document.getElementById('loan-purpose').value,
        loan_items: loanItemsJson
    };
    try {
        const res = await postData('/loans', data, null);  // 无文件
        alert(`借款申请创建成功！单据号: ${res.document_number}`);
        document.getElementById('loan-form').reset();
        loadLoanFormData();
    } catch(err) { alert('提交失败: '+err.message); }
});

//我的借款列表
async function loadMyLoans() {
    try {
        const loans = await fetchData('/loans?view_mode=my');
        const tbody = document.getElementById('loans-table-body');
        if (!loans.length) {
            tbody.innerHTML = '<tr><td colspan="10" class="empty-state">暂无借款申请</td></tr>';
            return;
        }
        let html = '';
        for (const l of loans) {
            const canDelete = (l.is_draft || (l.status === 'pending' && l.user_id === currentUser?.id && l.current_step === 1 && (!l.approvals || l.approvals.length === 0)));
            html += `
                <tr>
                    <td>${l.document_number}</td>
                    <td>${l.user_name}</td>
                    <td>${l.user_department || '-'}</td>
                    <td>${l.legal_person_name || '-'}</td>
                    <td>${l.currency_symbol || '¥'}${l.amount.toFixed(2)}</td>
                    <td>${l.payee_account_name || '-'}</td>
                    <td>${l.category}</td>
                    <td><span class="status ${l.is_draft ? 'draft' : l.status}">${l.is_draft ? '草稿' : getStatusText(l.status)}</span></td>
                    <td>${formatDate(l.created_at)}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="viewLoan(${l.id})">查看</button>
${l.is_draft ? `<button class="btn btn-primary btn-sm" onclick="editLoan(${l.id})">编辑</button>` : ''}
${canDelete ? `<button class="btn btn-danger btn-sm" onclick="deleteLoan(${l.id})">删除</button>` : ''}
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    } catch(e) {
        console.error(e);
    }
}

async function deleteLoan(id) {
    if (!confirm('确定删除此借款单吗？删除后不可恢复。')) return;
    try {
        const res = await deleteData(`/loans/${id}`);
        showToast(res.message || '删除成功', 'success');
        loadMyLoans();  // 刷新列表
    } catch(err) {
        showToast(err.message || '删除失败', 'error');
    }
}

// 借款审批列表加载
let currentLoanApprovalFilter = 'pending'; // 'pending' or 'all'

async function loadLoanApprovals() {
    const url = currentLoanApprovalFilter === 'pending' 
        ? '/loans?view_mode=pending_approval' 
        : '/loans?view_mode=all';
    const loans = await fetchData(url);
    const tbody = document.getElementById('loan-approvals-table-body');
    tbody.innerHTML = loans.length ? loans.map(l => `
        <tr>
            <td>${l.document_number}</td>
            <td>${l.user_name}</td>
            <td>${l.user_department || '-'}</td>
            <td>${l.legal_person_name || '-'}</td>
            <td>${l.currency_symbol || '¥'}${l.amount.toFixed(2)}</td>
            <td>${l.category}</td>
            <td><span class="status ${l.status}">${getStatusText(l.status)}</span></td>
            <td>${formatDate(l.created_at)}</td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="viewLoanForApproval(${l.id})">查看</button>
                ${currentLoanApprovalFilter === 'pending' ? `<button class="btn btn-primary btn-sm" onclick="viewLoanForApproval(${l.id})">审批</button>` : ''}
            </td>
        </tr>
    `).join('') : '<tr><td colspan="9" class="empty-state">暂无数据</td></tr>';
}

function filterLoanApprovals(filter) {
    currentLoanApprovalFilter = filter;
    document.querySelectorAll('#loan_approvals-panel .nav-tabs button').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    loadLoanApprovals();
}

// 查看借款详情（用于审批）
async function viewLoanForApproval(loanId) {
    const loan = await fetchData(`/loans/${loanId}`);
    currentLoanId = loanId;  // 复用全局变量
    const isApprover = canApproveLoan(loan);
    const isOwner = loan.user_id === currentUser?.id;
    document.getElementById('approval-detail').innerHTML = `
        <div class="approval-info">
            <div class="info-row"><span class="info-label">单据号</span><span class="info-value doc-number">${loan.document_number}</span></div>
            <div class="info-row"><span class="info-label">申请人</span><span class="info-value">${loan.user_name} (${loan.user_department||'-'})</span></div>
            <div class="info-row"><span class="info-label">法人主体</span><span class="info-value">${loan.legal_person_name||'-'}</span></div>
            <div class="info-row highlight"><span class="info-label">金额</span><span class="info-value amount">${loan.currency_symbol||'¥'}${loan.amount.toFixed(2)}</span></div>
            <div class="info-row"><span class="info-label">收款账户</span><span class="info-value">${loan.payee_account_name||'-'} (${loan.payee_account_number||'-'})</span></div>
            <div class="info-row"><span class="info-label">类别</span><span class="info-value">${loan.category}</span></div>
            <div class="info-row"><span class="info-label">借款用途</span><span class="info-value">${loan.purpose||'-'}</span></div>
            <div class="info-row"><span class="info-label">创建时间</span><span class="info-value">${formatDate(loan.created_at)}</span></div>
            <div class="info-row"><span class="info-label">当前状态</span><span class="info-value"><span class="status ${loan.status}">${getStatusText(loan.status)}</span> (第${loan.current_step}步)</span></div>
            ${loan.approvals.length ? `<div class="approval-history"><div class="history-title">审批记录</div><div class="history-list">${loan.approvals.map(a => `<div class="history-item"><div class="history-step">${a.step}</div><div class="history-content"><span class="history-name">${a.approver_name}</span><span class="history-action ${a.action}">${a.action==='approve'?'✓ 通过':'✗ 拒绝'}</span>${a.comment ? `<span class="history-comment">(${a.comment})</span>` : ''}</div></div>`).join('')}</div></div>` : ''}
        </div>
    `;
    const actionsDiv = document.getElementById('approval-actions');
    if (isApprover) {
        actionsDiv.style.display = 'flex';
        actionsDiv.innerHTML = `<button class="btn btn-success" onclick="submitLoanApproval('approve')">审批通过</button><button class="btn btn-danger" onclick="submitLoanApproval('reject')">驳回申请</button><input type="text" id="approval-comment" placeholder="审批意见（可选）" style="flex:1;">`;
    } else {
        actionsDiv.style.display = 'none';
    }
    document.getElementById('reedit-actions').style.display = 'none';
    document.getElementById('approval-modal').classList.add('show');
}

async function viewLoan(loanId) {
    const loan = await fetchData(`/loans/${loanId}`);
    currentLoanId = loanId;
    const isApprover = canApproveLoan(loan);
    const isOwner = loan.user_id === currentUser?.id;
    document.getElementById('approval-detail').innerHTML = `
        <div class="approval-info">
            <div class="info-row"><span class="info-label">单据号</span><span class="info-value doc-number">${loan.document_number}</span></div>
            <div class="info-row"><span class="info-label">申请人</span><span class="info-value">${loan.user_name} (${loan.user_department||'-'})</span></div>
            <div class="info-row"><span class="info-label">法人主体</span><span class="info-value">${loan.legal_person_name||'-'}</span></div>
            <div class="info-row highlight"><span class="info-label">金额</span><span class="info-value amount">${loan.currency_symbol||'¥'}${loan.amount.toFixed(2)}</span></div>
            <div class="info-row"><span class="info-label">收款账户</span><span class="info-value">${loan.payee_account_name||'-'} (${loan.payee_account_number||'-'})</span></div>
            <div class="info-row"><span class="info-label">类别</span><span class="info-value">${loan.category}</span></div>
            <div class="info-row"><span class="info-label">借款用途</span><span class="info-value">${loan.purpose||'-'}</span></div>
            <div class="info-row"><span class="info-label">创建时间</span><span class="info-value">${formatDate(loan.created_at)}</span></div>
            <div class="info-row"><span class="info-label">当前状态</span><span class="info-value"><span class="status ${loan.status}">${getStatusText(loan.status)}</span> (第${loan.current_step}步)</span></div>
            ${loan.approvals.length ? `<div class="approval-history"><div class="history-title">审批记录</div><div class="history-list">${loan.approvals.map(a => `<div class="history-item"><div class="history-step">${a.step}</div><div class="history-content"><span class="history-name">${a.approver_name}</span><span class="history-action ${a.action}">${a.action==='approve'?'✓ 通过':'✗ 拒绝'}</span>${a.comment ? `<span class="history-comment">(${a.comment})</span>` : ''}</div></div>`).join('')}</div></div>` : ''}
        </div>
    `;
    const actionsDiv = document.getElementById('approval-actions');
    if (isApprover) {
        actionsDiv.style.display = 'flex';
        actionsDiv.innerHTML = `<button class="btn btn-success" onclick="submitLoanApproval('approve')">审批通过</button><button class="btn btn-danger" onclick="submitLoanApproval('reject')">驳回申请</button><input type="text" id="approval-comment" placeholder="审批意见（可选）" style="flex:1;">`;
    } else actionsDiv.style.display = 'none';
    document.getElementById('reedit-actions').style.display = 'none';
    document.getElementById('approval-modal').classList.add('show');
}

function canApproveLoan(loan) {
    if (loan.status !== 'pending') return false;
    if (loan.user_id === currentUser?.id) return false;
    // 使用借款单自带的 required_role 字段（后端需要返回）
    return loan.required_role === currentUser?.role;
}

async function submitLoanApproval(action) {
    if (!currentLoanId) {
        alert('请先选择要审批的借款单');
        return;
    }
    const comment = document.getElementById('approval-comment')?.value || '';
    try {
        const res = await fetch(`${API_URL}/loan_approvals/${currentLoanId}`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type':'application/json' },
            body: JSON.stringify({ action, comment })
        });
        if (!res.ok) throw new Error((await res.json()).error);
        showToast((await res.json()).message, 'success');
        document.getElementById('approval-modal').classList.remove('show');
        loadMyLoans();
        // 如果当前在借款列表面板，刷新列表
        if (document.getElementById('loans-panel').style.display !== 'none') loadMyLoans();
    } catch(e) { showToast(e.message, 'error'); }
}

// ------------------------- 部门管理（平级列表，传统方式，用于兼容） -------------------------
async function loadDepartments() {
    const depts = await fetchData('/departments/all');
    const tbody = document.getElementById('departments-table-body');
    tbody.innerHTML = depts.length ? depts.map(d => `<tr><td>${d.name}</td><td>${d.code||'-'}</td><td>${d.description||'-'}</td><td><span class="status ${d.enabled?'enabled':'disabled'}">${d.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editDepartment(${d.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteDepartment(${d.id})">删除</button></td></tr>`).join('') : '<tr><td colspan="5" class="empty-state">暂无部门</td></tr>';
}
function showDepartmentModal(dept=null) {
    const modal = document.getElementById('department-modal');
    document.getElementById('department-modal-title').innerText = dept ? '编辑部门' : '新增部门';
    document.getElementById('department-id').value = dept?.id || '';
    document.getElementById('department-name').value = dept?.name || '';
    document.getElementById('department-code').value = dept?.code || '';
    document.getElementById('department-description').value = dept?.description || '';
    document.getElementById('department-enabled').value = dept?.enabled?.toString() || 'true';
    modal.classList.add('show');
}
async function editDepartment(id) { const d = await fetchData(`/departments/${id}`); showDepartmentModal(d); }
async function deleteDepartment(id) { if(confirm('确定删除？')) { await deleteData(`/departments/${id}`); loadDepartments(); } }
document.getElementById('department-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('department-id').value;
    const data = { name:document.getElementById('department-name').value, code:document.getElementById('department-code').value, description:document.getElementById('department-description').value, enabled:document.getElementById('department-enabled').value==='true' };
    if(id) await putData(`/departments/${id}`, data);
    else await postJson('/departments', data);
    closeDepartmentModal();
    loadDepartments();
});
function closeDepartmentModal() { document.getElementById('department-modal').classList.remove('show'); }

// ------------------------- 组织架构（树形，新功能） -------------------------
async function loadOrganizationTree() {
    try {
        const tree = await fetchData('/departments?mode=tree');
        const container = document.getElementById('org-tree-container');
        if (!container) return;
        if (!tree || tree.length === 0) { container.innerHTML = '<div class="empty-state">暂无部门，请点击“新增部门”创建</div>'; return; }
        function renderTree(nodes, level = 0) {
    let html = `<ul style="padding-left: ${level * 20}px;">`;
    for (const node of nodes) {
        const legal = node.legal_person_name ? ` (${escapeHtml(node.legal_person_name)})` : '';
        html += `
            <li>
                <div class="org-card">
                    <span class="org-name">${escapeHtml(node.name)}${legal}</span>
                    <span class="org-code">${escapeHtml(node.code || '')}</span>
                    <span class="status ${node.enabled ? 'enabled' : 'disabled'}">${node.enabled ? '启用' : '禁用'}</span>
                    <button class="btn btn-secondary btn-sm" onclick="editDepartmentById(${node.id})">编辑</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteDepartmentById(${node.id})">删除</button>
                </div>
                ${node.children && node.children.length ? renderTree(node.children, level + 1) : ''}
            </li>
        `;
    }
    html += '</ul>';
    return html;
}
        container.innerHTML = renderTree(tree);
    } catch(e) { console.error(e); document.getElementById('org-tree-container').innerHTML = '<div class="empty-state">加载失败</div>'; }
}
async function loadLegalPersonsForSelect(selectId, selectedId) {
    const persons = await fetchData('/legal_persons');
    const sel = document.getElementById(selectId);
    if (sel) sel.innerHTML = '<option value="">请选择法人</option>' + persons.map(p => `<option value="${p.id}" ${selectedId==p.id?'selected':''}>${escapeHtml(p.name)}</option>`).join('');
}
async function loadDepartmentsForParentSelect(currentId, selectedParentId) {
    const depts = await fetchData('/departments?mode=list');
    const sel = document.getElementById('department-parent');
    if (!sel) return;
    let html = '<option value="">无（顶级部门）</option>';
    for (const d of depts) {
        if (currentId && d.id == currentId) continue;
        html += `<option value="${d.id}" ${selectedParentId==d.id?'selected':''}>${escapeHtml(d.name)}</option>`;
    }
    sel.innerHTML = html;
}
function showDeptModal(dept=null) {
    const modal = document.getElementById('department-modal');
    if (!modal) return;
    document.getElementById('department-modal-title').innerText = dept ? '编辑部门' : '新增部门';
    document.getElementById('department-id').value = dept?.id || '';
    document.getElementById('department-name').value = dept?.name || '';
    document.getElementById('department-code').value = dept?.code || '';
    document.getElementById('department-description').value = dept?.description || '';
    document.getElementById('department-enabled').value = dept?.enabled?.toString() || 'true';
    loadLegalPersonsForSelect('department-legal-person', dept?.legal_person_id);
    loadDepartmentsForParentSelect(dept?.id, dept?.parent_id);
    modal.classList.add('show');
}
async function saveDepartment(event) {
    event.preventDefault();
    const id = document.getElementById('department-id').value;
    const data = {
        name: document.getElementById('department-name').value,
        code: document.getElementById('department-code').value,
        description: document.getElementById('department-description').value,
        enabled: document.getElementById('department-enabled').value === 'true',
        legal_person_id: document.getElementById('department-legal-person').value || null,
        parent_id: document.getElementById('department-parent').value || null
    };
    if (!data.name) { alert('部门名称不能为空'); return; }
    try {
        if (id) await putData(`/departments/${id}`, data);
        else await postJson('/departments', data);
        closeDepartmentModal();
        await loadOrganizationTree();
        await loadDepartmentsForSelect();
        alert('保存成功');
    } catch(e) { alert('保存失败: '+e.message); }
}
async function deleteDepartmentById(id) {
    if (!confirm('删除部门会同时删除其子部门，是否继续？')) return;
    try {
        await deleteData(`/departments/${id}`);
        await loadOrganizationTree();
        await loadDepartmentsForSelect();
    } catch(e) { alert('删除失败: '+e.message); }
}
async function editDepartmentById(id) {
    const dept = await fetchData(`/departments/${id}`);
    showDeptModal(dept);
}
async function loadDepartmentsForSelect() {
    try {
        const depts = await fetchData('/departments?mode=list');
        const claimDept = document.getElementById('claim-department');
        if (claimDept) {
            const old = claimDept.value;
            claimDept.innerHTML = '<option value="">请选择部门</option>' + depts.map(d => `<option value="${d.id}" ${old==d.id?'selected':''}>${escapeHtml(d.name)}</option>`).join('');
        }
        const userDept = document.getElementById('user-department');
        if (userDept) {
            const old = userDept.value;
            userDept.innerHTML = '<option value="">请选择部门</option>' + depts.map(d => `<option value="${d.id}" ${old==d.id?'selected':''}>${escapeHtml(d.name)}</option>`).join('');
        }
    } catch(e) { console.error(e); }
}
function escapeHtml(str) { if (!str) return ''; return str.replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'})[m]); }
document.getElementById('department-form')?.removeEventListener('submit', saveDepartment);
document.getElementById('department-form')?.addEventListener('submit', saveDepartment);

// ------------------------- 流程配置（简化，保留基本功能） -------------------------
async function loadFlows() {
    const flows = await fetchData('/flows');
    const tbody = document.getElementById('flows-table-body');
    tbody.innerHTML = flows.length ? flows.map(f => {
        const steps = JSON.parse(f.steps);
        return `<tr><td>${f.name}</td><td>${f.department||'全部部门'}</td><td>${steps.length}步</td><td><span class="status ${f.enabled?'enabled':'disabled'}">${f.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editFlow(${f.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteFlow(${f.id})">删除</button></td></tr>`;
    }).join('') : '<tr><td colspan="5" class="empty-state">暂无流程</td></tr>';
}
async function showFlowModal(flow=null) {
    try {
        const rolesResp = await fetchData('/roles');
        window.flowRoles = rolesResp;
    } catch(e) {
        console.error('加载角色失败', e);
        window.flowRoles = [];
    }
    const modal = document.getElementById('flow-modal');
    document.getElementById('flow-modal-title').innerText = flow ? '编辑审批流程' : '新建审批流程';
    document.getElementById('flow-id').value = flow?.id || '';
    document.getElementById('flow-name').value = flow?.name || '';
    document.getElementById('flow-department').value = flow?.department || '';
    const stepsDiv = document.getElementById('flow-steps');
    stepsDiv.innerHTML = '';
    if (flow) {
        const steps = JSON.parse(flow.steps);
        steps.forEach(s => addStep(s.step, s.role_code, s.description));
    } else {
        addStep(1, 'department_manager', '部门经理审批');
    }
    modal.classList.add('show');
}
function addStep(num=null, roleCode='', desc='') {
    const container = document.getElementById('flow-steps');
    const stepNum = num || (container.children.length+1);
    const div = document.createElement('div');
    div.className = 'step-item';
    div.style.display = 'flex'; div.style.gap = '0.5rem'; div.style.marginBottom = '0.5rem';
    let roleOptions = '<option value="">请选择角色</option>';
    (window.flowRoles || []).forEach(r => {
        roleOptions += `<option value="${r.code}" ${roleCode === r.code ? 'selected' : ''}>${r.name} (${r.code})</option>`;
    });
    div.innerHTML = `
        <input type="number" class="step-num" value="${stepNum}" readonly style="width:60px;">
        <select class="step-role">${roleOptions}</select>
        <input type="text" class="step-desc" placeholder="步骤描述" value="${desc}" style="flex:1;">
        <button type="button" class="btn btn-danger btn-sm" onclick="removeStep(this)">删除</button>
    `;
    container.appendChild(div);
}

function removeStep(btn) { if(document.getElementById('flow-steps').children.length>1) btn.parentElement.remove(); }
async function saveFlow(e) {
    e.preventDefault();
    const id = document.getElementById('flow-id').value;
    const steps = Array.from(document.querySelectorAll('.step-item')).map((item,i) => ({step: i+1,role_code: item.querySelector('.step-role').value,description: item.querySelector('.step-desc').value}));
    const data = { name:document.getElementById('flow-name').value, department:document.getElementById('flow-department').value, steps };
    if(id) await putData(`/flows/${id}`, data);
    else await postJson('/flows', data);
    closeFlowModal();
    loadFlows();
    alert('保存成功');
}
function closeFlowModal() { document.getElementById('flow-modal').classList.remove('show'); }
document.getElementById('flow-form')?.addEventListener('submit', saveFlow);
async function editFlow(id) { const f = await fetchData(`/flows/${id}`); showFlowModal(f); }
async function deleteFlow(id) { if(confirm('确定删除？')) { await deleteData(`/flows/${id}`); loadFlows(); } }

// ------------------------- 法人、币种、费用类型等基础数据管理（使用统一的 postData/putData） -------------------------
async function loadLegalPersons() {
    const persons = await fetchData('/legal_persons/all');
    const tbody = document.getElementById('legal-persons-table-body');
    tbody.innerHTML = persons.length ? persons.map(p => `<tr><td>${p.name}</td><td>${p.unified_code||'-'}</td><td>${p.address||'-'}</td><td>${p.contact||'-'}</td><td>${p.phone||'-'}</td><td><span class="status ${p.enabled?'enabled':'disabled'}">${p.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editLegalPerson(${p.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteLegalPerson(${p.id})">删除</button></td></tr>`).join('') : '<tr><td colspan="7" class="empty-state">暂无法人信息</td></tr>';
}
function showLegalPersonModal(p=null) {
    const modal = document.getElementById('legal-person-modal');
    document.getElementById('legal-person-modal-title').innerText = p ? '编辑法人信息' : '新增法人信息';
    document.getElementById('legal-person-id').value = p?.id || '';
    document.getElementById('legal-person-name').value = p?.name || '';
    document.getElementById('legal-person-code').value = p?.unified_code || '';
    document.getElementById('legal-person-address').value = p?.address || '';
    document.getElementById('legal-person-contact').value = p?.contact || '';
    document.getElementById('legal-person-phone').value = p?.phone || '';
    document.getElementById('legal-person-enabled').value = p?.enabled?.toString() || 'true';
    modal.classList.add('show');
}
async function saveLegalPerson(e) {
    e.preventDefault();
    const id = document.getElementById('legal-person-id').value;
    const data = { name:document.getElementById('legal-person-name').value, unified_code:document.getElementById('legal-person-code').value, address:document.getElementById('legal-person-address').value, contact:document.getElementById('legal-person-contact').value, phone:document.getElementById('legal-person-phone').value, enabled:document.getElementById('legal-person-enabled').value==='true' };
    if(id) await putData(`/legal_persons/${id}`, data);
    else await postJson('/legal_persons', data);
    closeLegalPersonModal();
    loadLegalPersons();
}
function closeLegalPersonModal() { document.getElementById('legal-person-modal').classList.remove('show'); }
async function editLegalPerson(id) { const p = await fetchData(`/legal_persons/${id}`); showLegalPersonModal(p); }
async function deleteLegalPerson(id) { if(confirm('确定删除？')) { await deleteData(`/legal_persons/${id}`); loadLegalPersons(); } }
document.getElementById('legal-person-form')?.addEventListener('submit', saveLegalPerson);

// 币种管理
async function loadCurrencies() { const list = await fetchData('/currencies/all'); const tbody = document.getElementById('currencies-table-body'); tbody.innerHTML = list.length ? list.map(c => `<tr><td>${c.code}</td><td>${c.name}</td><td>${c.symbol||'-'}</td><td>${c.rate}</td><td><span class="status ${c.enabled?'enabled':'disabled'}">${c.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editCurrency(${c.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteCurrency(${c.id})">删除</button></td></tr>`).join('') : '<tr><td colspan="6" class="empty-state">暂无币种</td></tr>'; }
function showCurrencyModal(c=null) { const modal = document.getElementById('currency-modal'); document.getElementById('currency-modal-title').innerText = c ? '编辑币种' : '新增币种'; document.getElementById('currency-id').value = c?.id || ''; document.getElementById('currency-code').value = c?.code || ''; document.getElementById('currency-name').value = c?.name || ''; document.getElementById('currency-symbol').value = c?.symbol || ''; document.getElementById('currency-rate').value = c?.rate || 1; document.getElementById('currency-enabled').value = c?.enabled?.toString() || 'true'; modal.classList.add('show'); }
async function saveCurrency(e) { e.preventDefault(); const id = document.getElementById('currency-id').value; const data = { code:document.getElementById('currency-code').value, name:document.getElementById('currency-name').value, symbol:document.getElementById('currency-symbol').value, rate:parseFloat(document.getElementById('currency-rate').value), enabled:document.getElementById('currency-enabled').value==='true' }; if(id) await putData(`/currencies/${id}`, data); else await postJson('/currencies', data); closeCurrencyModal(); loadCurrencies(); }
function closeCurrencyModal() { document.getElementById('currency-modal').classList.remove('show'); }
async function editCurrency(id) { const c = await fetchData(`/currencies/${id}`); showCurrencyModal(c); }
async function deleteCurrency(id) { if(confirm('确定删除？')) { await deleteData(`/currencies/${id}`); loadCurrencies(); } }
document.getElementById('currency-form')?.addEventListener('submit', saveCurrency);

// 费用类型
async function loadExpenseTypes() { const list = await fetchData('/expense_types/all'); const tbody = document.getElementById('expense-types-table-body'); tbody.innerHTML = list.length ? list.map(t => `<tr><td>${t.code}</td><td>${t.name}</td><td>${t.description||'-'}</td><td><span class="status ${t.enabled?'enabled':'disabled'}">${t.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editExpenseType(${t.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteExpenseType(${t.id})">删除</button></td></tr>`).join('') : '<tr><td colspan="5" class="empty-state">暂无费用类型</td></tr>'; }
function showExpenseTypeModal(t=null) { const modal = document.getElementById('expense-type-modal'); document.getElementById('expense-type-modal-title').innerText = t ? '编辑费用类型' : '新增费用类型'; document.getElementById('expense-type-id').value = t?.id || ''; document.getElementById('expense-type-code').value = t?.code || ''; document.getElementById('expense-type-name').value = t?.name || ''; document.getElementById('expense-type-description').value = t?.description || ''; document.getElementById('expense-type-enabled').value = t?.enabled?.toString() || 'true'; modal.classList.add('show'); }
async function saveExpenseType(e) { e.preventDefault(); const id = document.getElementById('expense-type-id').value; const data = { code:document.getElementById('expense-type-code').value, name:document.getElementById('expense-type-name').value, description:document.getElementById('expense-type-description').value, enabled:document.getElementById('expense-type-enabled').value==='true' }; if(id) await putData(`/expense_types/${id}`, data); else await postJson('/expense_types', data); closeExpenseTypeModal(); loadExpenseTypes(); }
function closeExpenseTypeModal() { document.getElementById('expense-type-modal').classList.remove('show'); }
async function editExpenseType(id) { const t = await fetchData(`/expense_types/${id}`); showExpenseTypeModal(t); }
async function deleteExpenseType(id) { if(confirm('确定删除？')) { await deleteData(`/expense_types/${id}`); loadExpenseTypes(); } }
document.getElementById('expense-type-form')?.addEventListener('submit', saveExpenseType);

// 业务所属
async function loadOperationTypes() { const list = await fetchData('/operation_types/all'); const tbody = document.getElementById('operation-types-table-body'); tbody.innerHTML = list.length ? list.map(t => `<tr><td>${t.code}</td><td>${t.name}</td><td>${t.description||'-'}</td><td><span class="status ${t.enabled?'enabled':'disabled'}">${t.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editOperationType(${t.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteOperationType(${t.id})">删除</button></td></tr>`).join('') : '<tr><td colspan="5" class="empty-state">暂无业务类型</td></tr>'; }
function showOperationTypeModal(t=null) { const modal = document.getElementById('operation-type-modal'); document.getElementById('operation-type-modal-title').innerText = t ? '编辑业务类型' : '新增业务类型'; document.getElementById('operation-type-id').value = t?.id || ''; document.getElementById('operation-type-code').value = t?.code || ''; document.getElementById('operation-type-name').value = t?.name || ''; document.getElementById('operation-type-description').value = t?.description || ''; document.getElementById('operation-type-enabled').value = t?.enabled?.toString() || 'true'; modal.classList.add('show'); }
async function saveOperationType(e) { e.preventDefault(); const id = document.getElementById('operation-type-id').value; const data = { code:document.getElementById('operation-type-code').value, name:document.getElementById('operation-type-name').value, description:document.getElementById('operation-type-description').value, enabled:document.getElementById('operation-type-enabled').value==='true' }; if(id) await putData(`/operation_types/${id}`, data); else await postJson('/operation_types', data); closeOperationTypeModal(); loadOperationTypes(); }
function closeOperationTypeModal() { document.getElementById('operation-type-modal').classList.remove('show'); }
async function editOperationType(id) { const t = await fetchData(`/operation_types/${id}`); showOperationTypeModal(t); }
async function deleteOperationType(id) { if(confirm('确定删除？')) { await deleteData(`/operation_types/${id}`); loadOperationTypes(); } }
document.getElementById('operation-type-form')?.addEventListener('submit', saveOperationType);

// 收款账户
async function loadPayeeAccounts() { const list = await fetchData('/payee_accounts'); const tbody = document.getElementById('payee-accounts-table-body'); tbody.innerHTML = list.length ? list.map(a => `<tr><td>${a.account_name}</td><td>${a.account_number}</td><td>${a.bank_short_name||'-'}</td><td>${a.bank_location||'-'}</td><td><span class="status ${a.enabled?'enabled':'disabled'}">${a.enabled?'启用':'禁用'}</span></td><td><button class="btn btn-secondary btn-sm" onclick="editPayeeAccount(${a.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deletePayeeAccount(${a.id})">删除</button></td></tr>`).join('') : '<tr><td colspan="6" class="empty-state">暂无收款信息</td></tr>'; }
function showPayeeAccountModal(a=null) { const modal = document.getElementById('payee-account-modal'); document.getElementById('payee-account-modal-title').innerText = a ? '编辑收款信息' : '新增收款信息'; document.getElementById('payee-account-id').value = a?.id || ''; document.getElementById('payee-account-name').value = a?.account_name || ''; document.getElementById('payee-account-number').value = a?.account_number || ''; document.getElementById('payee-bank-short-name').value = a?.bank_short_name || ''; document.getElementById('payee-bank-location').value = a?.bank_location || ''; document.getElementById('payee-account-enabled').value = a?.enabled?.toString() || 'true'; modal.classList.add('show'); }
async function savePayeeAccount(e) { e.preventDefault(); const id = document.getElementById('payee-account-id').value; const data = { account_name:document.getElementById('payee-account-name').value, account_number:document.getElementById('payee-account-number').value, bank_short_name:document.getElementById('payee-bank-short-name').value, bank_location:document.getElementById('payee-bank-location').value, enabled:document.getElementById('payee-account-enabled').value==='true' }; if(id) await putData(`/payee_accounts/${id}`, data); else await postJson('/payee_accounts', data); closePayeeAccountModal(); loadPayeeAccounts(); }
function closePayeeAccountModal() { document.getElementById('payee-account-modal').classList.remove('show'); }
async function editPayeeAccount(id) { const a = await fetchData(`/payee_accounts/${id}`); showPayeeAccountModal(a); }
async function deletePayeeAccount(id) { if(confirm('确定删除？')) { await deleteData(`/payee_accounts/${id}`); loadPayeeAccounts(); } }
document.getElementById('payee-account-form')?.addEventListener('submit', savePayeeAccount);
// 管理员加载全部收款账户
async function loadAllPayeeAccounts() {
    const list = await fetchData('/payee_accounts/all');
    const tbody = document.getElementById('payee-accounts-table-body');
    tbody.innerHTML = list.length ? list.map(a => `
        <tr>
            <td>${a.account_name}</td>
            <td>${a.account_number}</td>
            <td>${a.bank_short_name || '-'}</td>
            <td>${a.bank_location || '-'}</td>
            <td><span class="status ${a.enabled ? 'enabled' : 'disabled'}">${a.enabled ? '启用' : '禁用'}</span></td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="editPayeeAccount(${a.id})">编辑</button>
                <button class="btn btn-danger btn-sm" onclick="deletePayeeAccount(${a.id})">删除</button>
            </td>
        </table>
    `).join('') : '<tr><td colspan="6" class="empty-state">暂无收款信息</td></tr>';
}

// 用户管理
async function loadUsers() { const users = await fetchData('/users'); const tbody = document.getElementById('users-table-body'); tbody.innerHTML = users.map(u => `<tr><td>${u.name}</td><td>${u.email}</td><td>${u.username}</td><td>${u.role_name || u.role}</td><td>${u.department||'-'}</td><td><button class="btn btn-secondary btn-sm" onclick="editUser(${u.id})">编辑</button><button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id})">删除</button></td></tr>`).join(''); }

async function showUserModal(u=null) { const modal = document.getElementById('user-modal'); document.getElementById('user-modal-title').innerText = u ? '编辑用户' : '新增用户'; document.getElementById('user-id').value = u?.id || ''; document.getElementById('user-name').value = u?.name || ''; document.getElementById('user-email').value = u?.email || ''; document.getElementById('user-username').value = u?.username || ''; document.getElementById('user-password').value = ''; await loadRolesForSelect(u?.role_id); loadDepartmentsForUserModal(u?.department_id); modal.classList.add('show'); }
async function loadDepartmentsForUserModal(selectedId) { const depts = await fetchData('/departments'); const sel = document.getElementById('user-department'); if(sel) sel.innerHTML = '<option value="">请选择部门</option>' + depts.map(d => `<option value="${d.id}" ${selectedId==d.id?'selected':''}>${d.name}</option>`).join(''); }
async function loadRolesForSelect(selectedRoleId = null) {
    const roles = await fetchData('/roles');
    const sel = document.getElementById('user-role');
    if (!sel) return;
    let html = '<option value="">请选择角色</option>';
    roles.forEach(r => {
        html += `<option value="${r.id}" ${selectedRoleId == r.id ? 'selected' : ''}>${r.name} (${r.code})</option>`;
    });
    sel.innerHTML = html;
}
async function saveUser(e) { e.preventDefault(); const id = document.getElementById('user-id').value; const roleId = document.getElementById('user-role').value;
    if (!roleId) {
        alert('请选择一个角色');
        return;
    }const data = { name:document.getElementById('user-name').value, email:document.getElementById('user-email').value, username:document.getElementById('user-username').value, password:document.getElementById('user-password').value || undefined, role_id: roleId,department_id:document.getElementById('user-department').value || null }; if(id) await putData(`/users/${id}`, data); else await postJson('/users', data); closeUserModal(); loadUsers(); }
function closeUserModal() { document.getElementById('user-modal').classList.remove('show'); }
async function editUser(id) { const u = await fetchData(`/users/${id}`); showUserModal(u); }
async function deleteUser(id) { if(confirm('确定删除？')) { await deleteData(`/users/${id}`); loadUsers(); } }
document.getElementById('user-form')?.addEventListener('submit', saveUser);

// ------------------------- 角色管理 -------------------------
async function loadRoles() {
    const roles = await fetchData('/roles/all');
    const tbody = document.getElementById('roles-table-body');
    if (!tbody) return;
    tbody.innerHTML = roles.map(r => `
        <tr>
            <td>${r.name}</td>
            <td>${r.code}</td>
            <td>${r.description || '-'}</td>
            <td><span class="status ${r.enabled ? 'enabled' : 'disabled'}">${r.enabled ? '启用' : '禁用'}</span></td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="editRole(${r.id})">编辑</button>
                <button class="btn btn-danger btn-sm" onclick="deleteRole(${r.id})">删除</button>
            </td>
        </tr>
    `).join('');
}

function showRoleModal(role = null) {
    const modal = document.getElementById('role-modal');
    document.getElementById('role-modal-title').innerText = role ? '编辑角色' : '新增角色';
    document.getElementById('role-id').value = role?.id || '';
    document.getElementById('role-name').value = role?.name || '';
    document.getElementById('role-code').value = role?.code || '';
    document.getElementById('role-description').value = role?.description || '';
    document.getElementById('role-enabled').value = role?.enabled !== undefined ? role.enabled.toString() : 'true';
    modal.classList.add('show');
}

async function editRole(id) {
    const role = await fetchData(`/roles/${id}`);
    showRoleModal(role);
}

async function deleteRole(id) {
    if (!confirm('确定删除此角色吗？如果已被用户使用，将无法删除。')) return;
    try {
        await deleteData(`/roles/${id}`);
        loadRoles();
        // 刷新用户管理中的角色下拉框（如果有打开用户模态框，下次打开时会重新加载）
        await loadRolesForSelect();
    } catch (err) {
        alert(err.message);
    }
}

function closeRoleModal() {
    document.getElementById('role-modal').classList.remove('show');
}

document.getElementById('role-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('role-id').value;
    const data = {
        name: document.getElementById('role-name').value,
        code: document.getElementById('role-code').value,
        description: document.getElementById('role-description').value,
        enabled: document.getElementById('role-enabled').value === 'true'
    };
    if (id) {
        await putData(`/roles/${id}`, data);
    } else {
        await postJson('/roles', data);
    }
    closeRoleModal();
    loadRoles();
    loadRolesForSelect();  // 刷新用户管理中的角色下拉选项
}); 

// 登录、注销及面板切换
async function login(username, password) {
    const fd = new FormData(); fd.append('username', username); fd.append('password', password);
    const res = await fetch(`${API_URL}/login`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.json()).error || '登录失败');
    const data = await res.json();
    setToken(data.token);
    currentUser = data.user;
    showApp();
}
async function logout() { clearToken(); currentUser = null; showLogin(); }
async function checkLogin() {
    const token = getToken();
    if (!token) { showLogin(); return false; }
    try {
        const res = await fetch(`${API_URL}/current_user`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (res.ok) { currentUser = await res.json(); showApp(); return true; }
    } catch(e) {}
    showLogin();
    return false;
}
document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    try { await login(username, password); } catch(err) { alert(err.message); }
});

// ------------------------- 付款处理中心 -------------------------
let currentPaymentTab = 'unpaid';  // 'unpaid' or 'paid'
let paymentData = [];

async function loadPaymentCenter() {
    const status = currentPaymentTab === 'unpaid' ? 'unpaid' : 'paid';
    const data = await fetchData(`/payment_center?status=${status}`);
    paymentData = data;
    renderPaymentTable();
}

function renderPaymentTable() {
    const tbody = document.getElementById('payment-table-body');
    const toolbar = document.getElementById('payment-toolbar');
    const batchBtn = document.getElementById('batch-register-btn');
    if (currentPaymentTab === 'unpaid') {
        if (toolbar) toolbar.style.display = 'block';
        if (batchBtn) batchBtn.style.display = 'inline-block';
    } else {
        if (toolbar) toolbar.style.display = 'none';
    }

    if (!paymentData.length) {
        tbody.innerHTML = '<tr><td colspan="11" class="empty-state">暂无数据</td></tr>';
        const selectAll = document.getElementById('select-all');
        if (selectAll) selectAll.checked = false;
        const selectedCount = document.getElementById('selected-count');
        if (selectedCount) selectedCount.innerText = '';
        return;
    }

    tbody.innerHTML = paymentData.map(item => `
        <tr>
            <td>${currentPaymentTab === 'unpaid' ? `<input type="checkbox" class="payment-item-checkbox" data-type="${item.type}" data-id="${item.id}">` : ''}</td>
            <td>${item.type_name}</td>
            <td>${item.document_number}</td>
            <td>${item.applicant}</td>
            <td>${item.apply_date}</td>
            <td>${item.payee_name || '-'}</td>
            <td>${item.payee_account || '-'}</td>
            <td>${item.bank_name || '-'}</td>
            <td>${item.amount.toFixed(2)}</td>
            <td>${item.legal_person || '-'}</td>
            <td>
                ${currentPaymentTab === 'unpaid' 
                    ? `<button class="btn btn-primary btn-sm" onclick="singleRegisterPayment('${item.type}', ${item.id})">登记</button>`
                    : `<span>${item.payment_date || '-'}</span>`}
            </td>
        </tr>
    `).join('');

    // 绑定全选事件
    const selectAll = document.getElementById('select-all');
    if (selectAll) {
        selectAll.onchange = function() {
            document.querySelectorAll('.payment-item-checkbox').forEach(cb => cb.checked = this.checked);
            updateSelectedCount();
        };
    }
    // 绑定每个checkbox的change事件
    document.querySelectorAll('.payment-item-checkbox').forEach(cb => {
        cb.onchange = () => updateSelectedCount();
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const checked = document.querySelectorAll('.payment-item-checkbox:checked').length;
    const selectedSpan = document.getElementById('selected-count');
    if (selectedSpan) selectedSpan.innerText = checked ? `已选择 ${checked} 条` : '';
}

async function switchPaymentTab(tab) {
    currentPaymentTab = tab;
    // 切换tab按钮样式
    const btns = document.querySelectorAll('#payment_center-panel .nav-tabs button');
    btns.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    await loadPaymentCenter();
}

async function singleRegisterPayment(type, id) {
    let paymentDate = prompt('请输入付款日期 (格式: YYYY-MM-DD)，留空则使用今天', new Date().toISOString().slice(0,10));
    if (paymentDate === null) return;  // 用户点击取消
    if (paymentDate.trim() === '') paymentDate = new Date().toISOString().slice(0,10);
    if (!confirm(`确认登记该笔付款，付款日期为 ${paymentDate} 吗？`)) return;
    try {
        const res = await fetch(`${API_URL}/payment_register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${getToken()}` },
            body: JSON.stringify({ items: [{ type, id }], payment_date: paymentDate })
        });
        if (!res.ok) throw new Error((await res.json()).error);
        const result = await res.json();
        showToast(result.message, 'success');
        await loadPaymentCenter();
    } catch(e) {
        showToast(e.message, 'error');
    }
}

async function batchRegisterPayment() {
    const checkedBoxes = document.querySelectorAll('.payment-item-checkbox:checked');
    if (checkedBoxes.length === 0) {
        alert('请至少选择一条记录');
        return;
    }
    let paymentDate = prompt('请输入付款日期 (格式: YYYY-MM-DD)，留空则使用今天', new Date().toISOString().slice(0,10));
    if (paymentDate === null) return;
    if (paymentDate.trim() === '') paymentDate = new Date().toISOString().slice(0,10);
    const items = Array.from(checkedBoxes).map(cb => ({
        type: cb.dataset.type,
        id: parseInt(cb.dataset.id)
    }));
    try {
        const res = await fetch(`${API_URL}/payment_register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${getToken()}` },
            body: JSON.stringify({ items, payment_date: paymentDate })
        });
        if (!res.ok) throw new Error((await res.json()).error);
        const result = await res.json();
        showToast(result.message, 'success');
        await loadPaymentCenter();
    } catch(e) {
        showToast(e.message, 'error');
    }
}

function showPanel(panelId) {
    // 流程配置仅限管理员访问
    if (panelId === 'flows' && (!currentUser || currentUser.role !== 'admin')) {
        showToast('您无权访问流程配置', 'warning');
        return;
    }
    document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
    const panel = document.getElementById(`${panelId}-panel`);
    if (panel) panel.style.display = 'block';
    if (panelId === 'claims') loadClaims();
    else if (panelId === 'create') loadFormData();
    else if (panelId === 'approvals') loadApprovals();
    else if (panelId === 'purchase_create') loadPurchaseFormData();
    else if (panelId === 'my_purchases') loadMyPurchases();
    else if (panelId === 'purchase_approvals') loadPurchaseApprovals();
    else if (panelId === 'flows') loadFlows();
    else if (panelId === 'departments') loadDepartments();
    else if (panelId === 'legal_persons') loadLegalPersons();
    else if (panelId === 'expense_types') loadExpenseTypes();
    else if (panelId === 'operation_types') loadOperationTypes();
    else if (panelId === 'currencies') loadCurrencies();
    else if (panelId === 'payee_accounts') {
    if (currentUser && currentUser.role === 'admin') {
        loadAllPayeeAccounts();
    } else {
        loadPayeeAccounts();
    }
}
    else if (panelId === 'payment_center') {
        currentPaymentTab = 'unpaid';
        loadPaymentCenter();
    }
    else if (panelId === 'roles') loadRoles();
    else if (panelId === 'organization') loadOrganizationTree();
    else if (panelId === 'users') loadUsers();
    else if (panelId === 'loan_create') loadLoanFormData();
    else if (panelId === 'loans') loadMyLoans();
    else if (panelId === 'loan_approvals') loadLoanApprovals();
}

// 初始化默认一行报销费用明细
function initExpenseRows() {
    const tbody = document.getElementById('expense-items-body');
    if (tbody && tbody.children.length === 0) {
        addExpenseRow(); addExpenseRow();
    }
}
window.addEventListener('load', () => { initExpenseRows(); checkLogin(); });

function initLoanExpenseRows() {
    const tbody = document.getElementById('loan-expense-items-body');
    if (tbody && tbody.children.length === 0) {
        addLoanExpenseRow(); addLoanExpenseRow();
    }
}
window.addEventListener('load', () => { initExpenseRows(); initLoanExpenseRows(); checkLogin(); });

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}
function showToast(message, type = 'success') {
    const modal = document.getElementById('toast-modal');
    const icon = document.getElementById('toast-icon');
    const msg = document.getElementById('toast-message');
    
    icon.className = 'toast-icon';
    if (type === 'error') {
        icon.classList.add('error');
        icon.innerHTML = '✗';
    } else if (type === 'warning') {
        icon.classList.add('warning');
        icon.innerHTML = '⚠';
    } else {
        icon.innerHTML = '✓';
    }
    
    msg.textContent = message;
    modal.classList.add('show');
}
function closeToast() {
    document.getElementById('toast-modal').classList.remove('show');
}

// ------------------------- 资产采购申请 -------------------------
let purchaseItems = [];  // 存储采购明细
let purchaseContracts = [];

async function loadPurchaseFormData(draftId = null) {
    try {
        const persons = await fetchData('/legal_persons');
        const currencies = await fetchData('/currencies');
        const accounts = await fetchData('/payee_accounts');
        
        let purchaseData = null;
        if (draftId) {
            purchaseData = await fetchData(`/purchases/${draftId}`);
            window.editingPurchaseId = draftId;
            document.getElementById('purchase-document-number').value = purchaseData.document_number;
        } else {
            window.editingPurchaseId = null;
            const docNum = await fetchData('/next_purchase_number');
            document.getElementById('purchase-document-number').value = docNum.document_number;
        }
        
        if (currentUser) {
            document.getElementById('purchase-user-name').value = currentUser.name;
            document.getElementById('purchase-user-department').value = currentUser.department || '';
        }
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        document.getElementById('purchase-date').value = `${yyyy}-${mm}-${dd}`;
        
        document.getElementById('purchase-legal-person').innerHTML = '<option value="">请选择法人主体</option>' + persons.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
        document.getElementById('purchase-currency').innerHTML = currencies.map(c => `<option value="${c.id}">${c.code} - ${c.name}</option>`).join('');
        document.getElementById('purchase-payee-account').innerHTML = '<option value="">请选择收款账户</option>' + accounts.map(a => `<option value="${a.id}">${a.account_name} - ${a.bank_short_name||''}</option>`).join('');
        
        // 清空动态表格
        document.getElementById('contract-tbody').innerHTML = '';
        document.getElementById('purchase-item-tbody').innerHTML = '';
        
        if (purchaseData) {
            // 回填表单数据
            if (purchaseData.legal_person_id) document.getElementById('purchase-legal-person').value = purchaseData.legal_person_id;
            if (purchaseData.currency_id) document.getElementById('purchase-currency').value = purchaseData.currency_id;
            if (purchaseData.payment_remark) document.getElementById('purchase-payment-remark').value = purchaseData.payment_remark;
            // 恢复合同信息
            if (purchaseData.contracts && purchaseData.contracts.length) {
                purchaseData.contracts.forEach(c => addContractRow(c));
            } else {
                addContractRow();
            }
            // 恢复采购明细
            if (purchaseData.items && purchaseData.items.length) {
                purchaseData.items.forEach(item => addPurchaseItemRow(item));
            } else {
                addPurchaseItemRow();
            }
            // 恢复收款账户
            if (purchaseData.payee_account_id) document.getElementById('purchase-payee-account').value = purchaseData.payee_account_id;
            // 触发收款账户change事件以填充名称账号
            document.getElementById('purchase-payee-account').dispatchEvent(new Event('change'));
            // 恢复收款金额（合计会自动计算）
            calculatePurchaseTotal();
        } else {
            addContractRow();
            addPurchaseItemRow();
        }
    } catch(e) { console.error(e); }
}

function addContractRow(contract = null) {
    const tbody = document.getElementById('contract-tbody');
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="contract-number" value="${contract?.contract_number || ''}" style="width:100%;"></td>
        <td><input type="text" class="contract-name" value="${contract?.contract_name || ''}" style="width:100%;"></td>
        <td><input type="text" class="supplier-name" value="${contract?.supplier_name || ''}" style="width:100%;"></td>
        <td><button type="button" class="btn btn-danger btn-sm" onclick="removeContractRow(this)">删除</button></td>
    `;
    tbody.appendChild(tr);
}

function removeContractRow(btn) { btn.closest('tr').remove(); }

function addPurchaseItemRow(item = null) {
    const tbody = document.getElementById('purchase-item-tbody');
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="payment-unit" value="${item?.payment_unit || ''}" style="width:100%;"></td>
        <td>
            <select class="purchase-type" style="width:100%;">
                <option value="原材料">原材料</option>
                <option value="设备资产">设备资产</option>
                <option value="房产">房产</option>
                <option value="土地">土地</option>
                <option value="软件专利资产">软件专利资产</option>
                <option value="库存商品">库存商品</option>
                <option value="其他资产">其他资产</option>
            </select>
        </td>
        <td><input type="text" class="item-name" value="${item?.item_name || ''}" style="width:100%;"></td>
        <td><input type="number" class="quantity" value="${item?.quantity || 1}" style="width:80px;"></td>
        <td><input type="number" class="contract-total" step="0.01" value="${item?.contract_total_amount || 0}" oninput="validateItemAmount(this)"></td>
        <td><input type="number" class="requested-amount" step="0.01" value="${item?.requested_amount || 0}" oninput="validateItemAmount(this); calculatePurchaseTotal()"></td>
        <td><button type="button" class="btn btn-danger btn-sm" onclick="removePurchaseItemRow(this)">删除</button></td>
    `;
    if (item && item.purchase_type) tr.querySelector('.purchase-type').value = item.purchase_type;
    tbody.appendChild(tr);
    calculatePurchaseTotal();
}

function validateItemAmount(input) {
    const row = input.closest('tr');
    const contractTotal = parseFloat(row.querySelector('.contract-total').value) || 0;
    const requested = parseFloat(row.querySelector('.requested-amount').value) || 0;
    if (requested > contractTotal) {
        alert('本次申请付款金额不能大于合同总金额');
        row.querySelector('.requested-amount').value = contractTotal;
        calculatePurchaseTotal();
    }
}

function removePurchaseItemRow(btn) { btn.closest('tr').remove(); calculatePurchaseTotal(); }

function calculatePurchaseTotal() {
    let total = 0;
    document.querySelectorAll('#purchase-item-tbody .requested-amount').forEach(inp => {
        total += parseFloat(inp.value) || 0;
    });
    const symbol = document.getElementById('purchase-currency').selectedOptions[0]?.text?.split(' ')[0] || '¥';
    document.getElementById('purchase-total-amount').innerHTML = `${symbol}${total.toFixed(2)}`;
    document.getElementById('purchase-payee-amount').value = total.toFixed(2);
}

document.getElementById('purchase-currency')?.addEventListener('change', calculatePurchaseTotal);
document.getElementById('purchase-payee-account')?.addEventListener('change', function() {
    const acc = allAccounts.find(a => a.id == this.value);
    document.getElementById('purchase-payee-name').value = acc?.account_name || '';
    document.getElementById('purchase-payee-number').value = acc?.account_number || '';
});

document.getElementById('purchase-upload-area')?.addEventListener('click', () => document.getElementById('purchase-attachments').click());
document.getElementById('purchase-attachments')?.addEventListener('change', (e) => {
    const files = Array.from(e.target.files);
    document.getElementById('purchase-uploaded-files').innerHTML = files.map((f,i)=>`<div class="badge">${i+1}. ${f.name}</div>`).join('');
});

document.getElementById('purchase-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentUser || !currentUser.id) { alert('未登录'); return; }
    const contracts = [];
    document.querySelectorAll('#contract-tbody tr').forEach(row => {
        const contract_number = row.querySelector('.contract-number').value;
        const contract_name = row.querySelector('.contract-name').value;
        const supplier_name = row.querySelector('.supplier-name').value;
        if (contract_number || contract_name || supplier_name) {
            contracts.push({ contract_number, contract_name, supplier_name });
        }
    });
    const items = [];
    let hasError = false;
    document.querySelectorAll('#purchase-item-tbody tr').forEach(row => {
        const payment_unit = row.querySelector('.payment-unit').value;
        const purchase_type = row.querySelector('.purchase-type').value;
        const item_name = row.querySelector('.item-name').value;
        const quantity = parseInt(row.querySelector('.quantity').value) || 0;
        const contract_total_amount = parseFloat(row.querySelector('.contract-total').value) || 0;
        const requested_amount = parseFloat(row.querySelector('.requested-amount').value) || 0;
        if (requested_amount > contract_total_amount) {
            alert('存在本次申请付款金额大于合同总金额的记录，请修正');
            hasError = true;
            return;
        }
        items.push({ payment_unit, purchase_type, item_name, quantity, contract_total_amount, requested_amount });
    });
    if (hasError) return;
    if (items.length === 0) { alert('请至少添加一条采购明细'); return; }

    const data = {
        user_id: currentUser.id,
        department_id: currentUser.department_id || '',
        legal_person_id: document.getElementById('purchase-legal-person').value || '',
        currency_id: document.getElementById('purchase-currency').value,
        payment_remark: document.getElementById('purchase-payment-remark').value,
        contracts: JSON.stringify(contracts),
        items: JSON.stringify(items)
    };
    const files = Array.from(document.getElementById('purchase-attachments').files);
    try {
        const res = await postData('/purchases', data, files);
        alert(`采购申请创建成功！单据号: ${res.document_number}`);
        document.getElementById('purchase-form').reset();
        loadPurchaseFormData();
    } catch(err) { alert('提交失败: '+err.message); }
});

async function savePurchaseDraft() {
    if (window.editingPurchaseId) {
        await updatePurchaseDraft();
        return;
    }    
    if (!currentUser || !currentUser.id) { alert('未登录'); return; }
    const contracts = [];
    document.querySelectorAll('#contract-tbody tr').forEach(row => {
        const contract_number = row.querySelector('.contract-number').value;
        const contract_name = row.querySelector('.contract-name').value;
        const supplier_name = row.querySelector('.supplier-name').value;
        if (contract_number || contract_name || supplier_name) {
            contracts.push({ contract_number, contract_name, supplier_name });
        }
    });
    const items = [];
    let hasError = false;
    document.querySelectorAll('#purchase-item-tbody tr').forEach(row => {
        const payment_unit = row.querySelector('.payment-unit').value;
        const purchase_type = row.querySelector('.purchase-type').value;
        const item_name = row.querySelector('.item-name').value;
        const quantity = parseInt(row.querySelector('.quantity').value) || 0;
        const contract_total_amount = parseFloat(row.querySelector('.contract-total').value) || 0;
        const requested_amount = parseFloat(row.querySelector('.requested-amount').value) || 0;
        if (requested_amount > contract_total_amount) {
            alert('存在本次申请付款金额大于合同总金额的记录，请修正');
            hasError = true;
            return;
        }
        items.push({ payment_unit, purchase_type, item_name, quantity, contract_total_amount, requested_amount });
    });
    if (hasError) return;
    if (items.length === 0) { alert('请至少添加一条采购明细'); return; }

    const data = {
        user_id: currentUser.id,
        department_id: currentUser.department_id || '',
        legal_person_id: document.getElementById('purchase-legal-person').value || '',
        currency_id: document.getElementById('purchase-currency').value,
        payment_remark: document.getElementById('purchase-payment-remark').value,
        contracts: JSON.stringify(contracts),
        items: JSON.stringify(items),
        is_draft: true
    };
    const files = Array.from(document.getElementById('purchase-attachments').files);
    try {
        const res = await postData('/purchases', data, files);
        alert('草稿保存成功！');
        document.getElementById('purchase-form').reset();
        loadPurchaseFormData();
        showPanel('my_purchases');
    } catch(err) { alert('保存失败: '+err.message); }
}

async function updatePurchaseDraft() {
    if (!window.editingPurchaseId) return;
    // 收集合同和明细，和新建时一样
    const contracts = [];
    document.querySelectorAll('#contract-tbody tr').forEach(row => {
        const contract_number = row.querySelector('.contract-number').value;
        const contract_name = row.querySelector('.contract-name').value;
        const supplier_name = row.querySelector('.supplier-name').value;
        if (contract_number || contract_name || supplier_name) {
            contracts.push({ contract_number, contract_name, supplier_name });
        }
    });
    const items = [];
    let hasError = false;
    document.querySelectorAll('#purchase-item-tbody tr').forEach(row => {
        const payment_unit = row.querySelector('.payment-unit').value;
        const purchase_type = row.querySelector('.purchase-type').value;
        const item_name = row.querySelector('.item-name').value;
        const quantity = parseInt(row.querySelector('.quantity').value) || 0;
        const contract_total_amount = parseFloat(row.querySelector('.contract-total').value) || 0;
        const requested_amount = parseFloat(row.querySelector('.requested-amount').value) || 0;
        if (requested_amount > contract_total_amount) {
            alert('存在本次申请付款金额大于合同总金额的记录，请修正');
            hasError = true;
            return;
        }
        items.push({ payment_unit, purchase_type, item_name, quantity, contract_total_amount, requested_amount });
    });
    if (hasError) return;
    if (items.length === 0) { alert('请至少添加一条采购明细'); return; }

    const data = {
        legal_person_id: document.getElementById('purchase-legal-person').value || '',
        currency_id: document.getElementById('purchase-currency').value,
        payment_remark: document.getElementById('purchase-payment-remark').value,
        contracts: JSON.stringify(contracts),
        items: JSON.stringify(items)
    };
    try {
        const res = await putData(`/purchases/draft/${window.editingPurchaseId}`, data);
        alert(res.message);
        delete window.editingPurchaseId;
        document.getElementById('purchase-form').onsubmit = window.originalPurchaseSubmit;
        showPanel('my_purchases');
        loadMyPurchases();
    } catch(err) { alert('更新失败: '+err.message); }
}

async function loadMyPurchases() {
    const purchases = await fetchData('/purchases?view_mode=my');
    const tbody = document.getElementById('my-purchases-table-body');
    tbody.innerHTML = purchases.length ? purchases.map(p => `
        <tr>
            <td>${p.document_number}</td>
            <td>${p.user_name}</td>
            <td>${p.user_department || '-'}</td>
            <td>${p.legal_person_name || '-'}</td>
            <td>${p.currency_symbol}${p.total_amount.toFixed(2)}</td>
            <td><span class="status ${p.is_draft ? 'draft' : p.status}">${p.is_draft ? '草稿' : getStatusText(p.status)}</span></td>
            <td>${formatDate(p.created_at)}</td>
            <td>
    <button class="btn btn-secondary btn-sm" onclick="viewPurchase(${p.id})">查看</button>
    ${p.is_draft ? `<button class="btn btn-primary btn-sm" onclick="editPurchase(${p.id})">编辑</button>` : ''}
</td>
        </tr>
    `).join('') : '<tr><td colspan="8" class="empty-state">暂无采购申请</td></tr>';
}

async function viewPurchase(purchaseId) {
    const purchase = await fetchData(`/purchases/${purchaseId}`);
    currentPurchaseId = purchaseId;
    const isApprover = canApprovePurchase(purchase);
    const isOwner = purchase.user_id === currentUser?.id;
    let itemsHtml = '';
    purchase.items.forEach(item => {
        itemsHtml += `<tr><td>${item.payment_unit||'-'}</td><td>${item.purchase_type||'-'}</td><td>${item.item_name||'-'}</td><td>${item.quantity||0}</td><td>${purchase.currency_symbol||'¥'}${(item.contract_total_amount||0).toFixed(2)}</td><td>${purchase.currency_symbol||'¥'}${(item.requested_amount||0).toFixed(2)}</td></tr>`;
    });
    let contractsHtml = '';
    purchase.contracts.forEach(c => {
        contractsHtml += `<tr><td>${c.contract_number||'-'}</td><td>${c.contract_name||'-'}</td><td>${c.supplier_name||'-'}</td></tr>`;
    });
    document.getElementById('approval-detail').innerHTML = `
        <div class="approval-info">
            <div class="info-row"><span class="info-label">单据号</span><span class="info-value doc-number">${purchase.document_number}</span></div>
            <div class="info-row"><span class="info-label">申请人</span><span class="info-value">${purchase.user_name} (${purchase.user_department||'-'})</span></div>
            <div class="info-row"><span class="info-label">法人主体</span><span class="info-value">${purchase.legal_person_name||'-'}</span></div>
            <div class="info-row highlight"><span class="info-label">总金额</span><span class="info-value amount">${purchase.currency_symbol||'¥'}${(purchase.items.reduce((s,i)=>s+i.requested_amount,0)).toFixed(2)}</span></div>
            <div class="info-row"><span class="info-label">付款备注</span><span class="info-value">${purchase.payment_remark||'-'}</span></div>
            <div class="info-row"><span class="info-label">创建时间</span><span class="info-value">${formatDate(purchase.created_at)}</span></div>
            ${contractsHtml ? `<div class="info-row"><span class="info-label">合同信息</span><div class="info-value"><table class="table">${contractsHtml}</table></div></div>` : ''}
            ${itemsHtml ? `<div class="info-row"><span class="info-label">采购明细</span><div class="info-value"><table class="table"><thead><tr><th>申请付款单位</th><th>采购类型</th><th>物品名称</th><th>数量</th><th>合同总金额</th><th>申请付款金额</th></tr></thead><tbody>${itemsHtml}</tbody></table></div></div>` : ''}
            ${purchase.attachments.length ? `<div class="info-row"><span class="info-label">附件</span><div class="info-value">${purchase.attachments.map(a => `<a href="${API_URL.replace('/api','')}/uploads/${a.filename}" target="_blank">${a.original_name}</a>`).join(', ')}</div></div>` : ''}
            <div class="info-row"><span class="info-label">当前状态</span><span class="info-value"><span class="status ${purchase.status}">${getStatusText(purchase.status)}</span> (第${purchase.current_step}步)</span></div>
            ${purchase.approvals.length ? `<div class="approval-history"><div class="history-title">审批记录</div>${purchase.approvals.map(a => `<div><span>${a.approver_name}</span> ${a.action==='approve'?'✓':'✗'} ${a.comment ? '('+a.comment+')' : ''}</div>`).join('')}</div>` : ''}
        </div>
    `;
    const actionsDiv = document.getElementById('approval-actions');
    if (isApprover) {
        actionsDiv.style.display = 'flex';
        actionsDiv.innerHTML = `<button class="btn btn-success" onclick="submitPurchaseApproval('approve')">审批通过</button><button class="btn btn-danger" onclick="submitPurchaseApproval('reject')">驳回申请</button><input type="text" id="approval-comment" placeholder="审批意见（可选）" style="flex:1;">`;
    } else actionsDiv.style.display = 'none';
    document.getElementById('reedit-actions').style.display = 'none';
    document.getElementById('approval-modal').classList.add('show');
}

function canApprovePurchase(purchase) {
    if (purchase.status !== 'pending') return false;
    if (purchase.user_id === currentUser?.id) return false;
    return purchase.required_role === currentUser?.role;
}

async function submitPurchaseApproval(action) {
    const comment = document.getElementById('approval-comment')?.value || '';
    try {
        const res = await fetch(`${API_URL}/purchase_approvals/${currentPurchaseId}`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type':'application/json' },
            body: JSON.stringify({ action, comment })
        });
        if (!res.ok) throw new Error((await res.json()).error);
        showToast((await res.json()).message, 'success');
        document.getElementById('approval-modal').classList.remove('show');
        // 刷新相关列表
        if (document.getElementById('my_purchases-panel').style.display !== 'none') loadMyPurchases();
        if (document.getElementById('purchase_approvals-panel').style.display !== 'none') loadPurchaseApprovals();
    } catch(e) { showToast(e.message, 'error'); }
}

let currentPurchaseApprovalFilter = 'pending';
async function loadPurchaseApprovals() {
    const url = currentPurchaseApprovalFilter === 'pending' ? '/purchases?view_mode=pending_approval' : '/purchases?view_mode=all';
    const purchases = await fetchData(url);
    const tbody = document.getElementById('purchase-approvals-table-body');
    tbody.innerHTML = purchases.length ? purchases.map(p => `
        <tr>
            <td>${p.document_number}</td>
            <td>${p.user_name}</td>
            <td>${p.user_department || '-'}</td>
            <td>${p.legal_person_name || '-'}</td>
            <td>${p.currency_symbol}${p.total_amount.toFixed(2)}</td>
            <td><span class="status ${p.status}">${getStatusText(p.status)}</span></td>
            <td>${formatDate(p.created_at)}</td>
            <td><button class="btn btn-secondary btn-sm" onclick="viewPurchase(${p.id})">查看</button>${currentPurchaseApprovalFilter === 'pending' ? `<button class="btn btn-primary btn-sm" onclick="viewPurchase(${p.id})">审批</button>` : ''}</td>
        </tr>
    `).join('') : '<tr><td colspan="8" class="empty-state">暂无数据</td></tr>';
}
function filterPurchaseApprovals(filter) {
    currentPurchaseApprovalFilter = filter;
    document.querySelectorAll('#purchase_approvals-panel .nav-tabs button').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    loadPurchaseApprovals();
}

// 报销草稿保存
async function saveClaimDraft() {
    // 如果是编辑模式，调用更新
    if (window.editingClaimId) {
        await updateClaimDraft();
        return;
    }
    // 收集报销费用明细
    const expenseItems = [];
    document.querySelectorAll('#expense-items-body tr').forEach(row => {
        const operationType = row.querySelector('.operation-type').value;
        const category = row.querySelector('.expense-category').value;
        const amount = parseFloat(row.querySelector('.expense-amount').value) || 0;
        expenseItems.push({ operationType, category, amount });
    });
    const expenseItemsJson = JSON.stringify(expenseItems);

    // 收集表单数据（与正式提交相同，但 is_draft=true）
    const rows = document.querySelectorAll('#expense-items-body tr');
    let total = 0, mainCat = '';
    rows.forEach(row => {
        const amt = parseFloat(row.querySelector('.expense-amount').value) || 0;
        total += amt;
        if (!mainCat) mainCat = row.querySelector('.expense-category').value;
    });
    if (!currentUser || !currentUser.id) { alert('未登录'); return; }
    const userId = currentUser.id;

    // 收集冲账明细
    const loanDetails = [];
    document.querySelectorAll('#loan-offset-tbody tr').forEach(row => {
        const loanSelect = row.querySelector('.loan-select');
        const offsetInput = row.querySelector('.offset-amount');
        if (loanSelect && loanSelect.value && parseFloat(offsetInput.value) > 0) {
            loanDetails.push({
                loan_id: parseInt(loanSelect.value),
                amount: parseFloat(offsetInput.value)
            });
        }
    });
    const loanDetailsJson = JSON.stringify(loanDetails);

    const data = {
        user_id: userId,
        department_id: document.getElementById('claim-department').value || '',
        legal_person_id: document.getElementById('claim-legal-person').value || '',
        currency_id: document.getElementById('claim-currency').value,
        payee_account_id: document.getElementById('claim-payee-account').value || '',
        amount: total,
        category: mainCat,
        description: document.getElementById('claim-description').value,
        expense_items: expenseItemsJson,
        loan_details: loanDetailsJson,
        is_draft: true
    };
    const files = Array.from(document.getElementById('receipt-files').files);
    try {
        const res = await postData('/claims', data, files);
        alert('草稿保存成功！');
        document.getElementById('claim-form').reset();
        loadFormData();
        showPanel('claims');
    } catch(err) { alert('保存失败: '+err.message); }
}

async function saveLoanDraft() {
    // 如果是编辑模式，调用更新
    if (window.editingLoanId) {
        await updateLoanDraft();
        return;
    }    
    const rows = document.querySelectorAll('#loan-expense-items-body tr');
    let total = 0, mainCat = '';
    const loanItems = [];
    rows.forEach(row => {
        const operationType = row.querySelector('.loan-operation-type').value;
        const category = row.querySelector('.loan-category').value;
        const amt = parseFloat(row.querySelector('.loan-amount').value) || 0;
        total += amt;
        if(!mainCat) mainCat = category;
        loanItems.push({ operationType, category, amount: amt });
    });
    const loanItemsJson = JSON.stringify(loanItems);
    if(total <= 0) { alert('请输入借款金额'); return; }
    if (!currentUser || !currentUser.id) { alert('未登录'); return; }
    const userId = currentUser.id;
    const data = {
        user_id: userId,
        department_id: document.getElementById('loan-department').value || '',
        legal_person_id: document.getElementById('loan-legal-person').value || '',
        currency_id: document.getElementById('loan-currency').value,
        payee_account_id: document.getElementById('loan-payee-account').value || '',
        amount: total,
        category: mainCat,
        purpose: document.getElementById('loan-purpose').value,
        loan_items: loanItemsJson,
        is_draft: true
    };
    try {
        const res = await postData('/loans', data, null);
        alert('草稿保存成功！');
        document.getElementById('loan-form').reset();
        loadLoanFormData();
        showPanel('loans');
    } catch(err) { alert('保存失败: '+err.message); }
}

async function updateLoanDraft() {
    if (!window.editingLoanId) return;
    // 收集借款明细
    const loanItems = [];
    document.querySelectorAll('#loan-expense-items-body tr').forEach(row => {
        const operationType = row.querySelector('.loan-operation-type').value;
        const category = row.querySelector('.loan-category').value;
        const amount = parseFloat(row.querySelector('.loan-amount').value) || 0;
        loanItems.push({ operationType, category, amount });
    });
    const loanItemsJson = JSON.stringify(loanItems);
    let total = 0;
    loanItems.forEach(item => total += item.amount);
    
    const data = {
        amount: total,
        purpose: document.getElementById('loan-purpose').value,
        category: loanItems[0]?.category || '其他',
        legal_person_id: document.getElementById('loan-legal-person').value || '',
        currency_id: document.getElementById('loan-currency').value,
        payee_account_id: document.getElementById('loan-payee-account').value || '',
        department_id: document.getElementById('loan-department').value || '',
        loan_items: loanItemsJson
    };
    try {
        const res = await putData(`/loans/draft/${window.editingLoanId}`, data);
        alert(res.message);
        delete window.editingLoanId;
        document.getElementById('loan-form').onsubmit = window.originalLoanSubmit;
        showPanel('loans');
        loadMyLoans();
    } catch(err) { alert('更新失败: '+err.message); }
}

