import json
from pathlib import Path
from datetime import datetime, timedelta

session_id = "demo01"

records = [
    # JOIN相关 - 2对1错
    {"timestamp": (datetime.now() - timedelta(hours=8)).isoformat(),
     "question": "INNER JOIN和LEFT JOIN的区别", "keywords": ["INNER JOIN", "LEFT JOIN", "NULL"],
     "answer": "INNER JOIN返回匹配行，LEFT JOIN返回左表所有行", "result": "校验通过",
     "hits": ["INNER JOIN", "LEFT JOIN"], "feedback": "正确"},
    {"timestamp": (datetime.now() - timedelta(hours=7)).isoformat(),
     "question": "LEFT JOIN的特点", "keywords": ["LEFT JOIN", "NULL", "连接"],
     "answer": "不知道", "result": "校验未通过",
     "hits": [], "feedback": "LEFT JOIN会保留左表所有行，右表无匹配填NULL"},
    {"timestamp": (datetime.now() - timedelta(hours=6)).isoformat(),
     "question": "JOIN查询练习", "keywords": ["LEFT JOIN", "NULL", "连接"],
     "answer": "LEFT JOIN左表全保留，无匹配补NULL", "result": "校验通过",
     "hits": ["LEFT JOIN", "NULL", "连接"], "feedback": "正确"},
    # ACID - 1对2错
    {"timestamp": (datetime.now() - timedelta(hours=6)).isoformat(),
     "question": "事务ACID特性", "keywords": ["原子性", "一致性", "隔离性", "持久性"],
     "answer": "原子性和一致性", "result": "校验未通过",
     "hits": ["原子性", "一致性"], "feedback": "漏掉隔离性和持久性"},
    {"timestamp": (datetime.now() - timedelta(hours=5)).isoformat(),
     "question": "ACID四个特性", "keywords": ["原子性", "一致性", "隔离性", "持久性"],
     "answer": "还是不太记得", "result": "校验未通过",
     "hits": [], "feedback": "需要记住ACID四个特性"},
    {"timestamp": (datetime.now() - timedelta(hours=4)).isoformat(),
     "question": "再次考察ACID", "keywords": ["原子性", "一致性", "隔离性", "持久性"],
     "answer": "原子性、一致性、隔离性、持久性", "result": "校验通过",
     "hits": ["原子性", "一致性", "隔离性", "持久性"], "feedback": "全部正确"},
    # GROUP BY - 2对1错
    {"timestamp": (datetime.now() - timedelta(hours=4)).isoformat(),
     "question": "GROUP BY和HAVING", "keywords": ["GROUP BY", "HAVING", "聚合", "分组"],
     "answer": "GROUP BY分组，HAVING过滤分组结果", "result": "校验通过",
     "hits": ["GROUP BY", "HAVING", "分组"], "feedback": "正确"},
    {"timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
     "question": "HAVING和WHERE区别", "keywords": ["GROUP BY", "HAVING", "聚合"],
     "answer": "不太清楚", "result": "校验未通过",
     "hits": [], "feedback": "HAVING作用于分组后，WHERE作用于分组前"},
    {"timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
     "question": "聚合查询", "keywords": ["GROUP BY", "HAVING", "聚合"],
     "answer": "GROUP BY分组，HAVING筛选聚合结果", "result": "校验通过",
     "hits": ["GROUP BY", "HAVING", "聚合"], "feedback": "完全正确"},
    # 索引 - 3对0错
    {"timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
     "question": "索引的作用", "keywords": ["索引", "查询速度", "B树"],
     "answer": "索引加快查询速度", "result": "校验通过",
     "hits": ["索引", "查询速度"], "feedback": "基本正确"},
    {"timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
     "question": "索引底层结构", "keywords": ["索引", "B树", "查询速度"],
     "answer": "索引用B树实现，提升查询性能", "result": "校验通过",
     "hits": ["索引", "B树", "查询速度"], "feedback": "正确"},
    # SQL注入 - 0对2错
    {"timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
     "question": "SQL注入防范", "keywords": ["SQL注入", "参数化查询", "安全"],
     "answer": "不知道怎么防", "result": "校验未通过",
     "hits": [], "feedback": "应使用参数化查询防止SQL注入"},
    {"timestamp": (datetime.now() - timedelta(minutes=30)).isoformat(),
     "question": "参数化查询", "keywords": ["SQL注入", "参数化查询", "安全"],
     "answer": "用拼接字符串", "result": "校验未通过",
     "hits": [], "feedback": "字符串拼接正是SQL注入的来源，应用参数化查询"},
    # 主外键 - 2对1错
    {"timestamp": (datetime.now() - timedelta(minutes=20)).isoformat(),
     "question": "主键和外键区别", "keywords": ["主键", "外键", "唯一", "关联"],
     "answer": "主键唯一标识记录，外键关联其他表", "result": "校验通过",
     "hits": ["主键", "外键", "唯一", "关联"], "feedback": "正确"},
    {"timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
     "question": "外键约束", "keywords": ["主键", "外键", "关联"],
     "answer": "忘了", "result": "校验未通过",
     "hits": [], "feedback": "外键必须引用另一张表的主键"},
    {"timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
     "question": "再次练习主外键", "keywords": ["主键", "外键", "关联"],
     "answer": "外键引用另一张表的主键，建立表间关联", "result": "校验通过",
     "hits": ["主键", "外键", "关联"], "feedback": "正确"},
]

db_path = Path("learning_db.json")
if db_path.exists():
    db = json.loads(db_path.read_text(encoding="utf-8"))
else:
    db = {}

db[session_id] = records
db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ 已写入 {len(records)} 条测试记录，session_id={session_id}")
print(f"   正确：{sum(1 for r in records if r['result'] == '校验通过')} 道")
print(f"   错误：{sum(1 for r in records if r['result'] != '校验通过')} 道")
print(f"\n演示时请在侧边栏将会话ID设置为：{session_id}")
