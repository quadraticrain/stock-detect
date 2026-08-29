"""清理旧裁员数据，使用v2重新收集"""
import sys
sys.path.insert(0, 'stock_push')
from layoff import get_db_connection

conn = get_db_connection()
with conn.cursor() as cur:
    # 查看当前数据量
    cur.execute("SELECT COUNT(*) FROM layoff_quarterly_data WHERE year=2026 AND quarter='Q2'")
    count = cur.fetchone()[0]
    print(f"当前2026 Q2数据: {count} 条")

    # 删除旧数据
    cur.execute("DELETE FROM layoff_quarterly_data WHERE year=2026 AND quarter='Q2'")
    print(f"已清理 2026 Q2 数据")

    # 重置表结构（添加confidence字段如果不存在）
    try:
        cur.execute("ALTER TABLE layoff_quarterly_data ADD COLUMN confidence VARCHAR(20) DEFAULT 'medium'")
        print("已添加 confidence 字段")
    except:
        print("confidence 字段已存在")

conn.commit()
conn.close()
print("清理完成，可以重新收集数据")
