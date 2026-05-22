# etl_simulate.py
# 作用：从报销系统数据库提取已付款单据，按部门+费用类型汇总，输出到 analytics.db

import sqlite3
import pandas as pd
import os
from datetime import datetime

# 1. 定义路径
source_db = r"F:\个人私物\AI开发\expense-system\backend\instance\expense.db"
target_db = r"F:\个人私物\AI开发\expense-system\backend\analytics.db"   # 生成的新数据库

# 2. 连接源数据库
print("正在连接源数据库...")
conn_src = sqlite3.connect(source_db)

# 3. 写 SQL 查询：只抓已付款单据，关联部门名称，按部门和费用类型汇总
#    条件：status = 'approved' 且 payment_date 不为空
sql = """
SELECT 
    d.name AS department_name,
    ec.category AS expense_category,
    SUM(ec.amount) AS total_amount,
    COUNT(ec.id) AS record_count
FROM expense_claim ec
LEFT JOIN department d ON ec.department_id = d.id
WHERE ec.status = 'approved'
  AND ec.payment_date IS NOT NULL
GROUP BY d.name, ec.category
ORDER BY d.name, total_amount DESC;
"""

print("正在提取数据并计算汇总...")
df = pd.read_sql_query(sql, conn_src)
conn_src.close()

# 4. 显示前几行（检查结果）
print("汇总结果如下（前5行）：")
print(df.head())

# 5. 写入目标数据库
print(f"正在写入 {target_db} ...")
conn_tgt = sqlite3.connect(target_db)
df.to_sql('dept_expense_summary', conn_tgt, if_exists='replace', index=False)
conn_tgt.close()

# 6. 增加一个时间戳表，记录最后一次更新
conn_tgt = sqlite3.connect(target_db)
conn_tgt.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT, value TEXT)")
conn_tgt.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                 ("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
conn_tgt.commit()
conn_tgt.close()

print("\n✅ 完成！生成的文件位于：", target_db)
print("你可以用任何 SQLite 浏览器打开查看 dept_expense_summary 表。")