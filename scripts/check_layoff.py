"""检查当前裁员数据质量"""
import sys
sys.path.insert(0, 'stock_push')
from layoff import get_db_connection

conn = get_db_connection()
with conn.cursor() as cur:
    cur.execute("""
        SELECT ticker, company_name, layoff_count, layoff_percent, note
        FROM layoff_quarterly_data
        WHERE year=2026 AND quarter='Q2' AND layoff_count IS NOT NULL
        ORDER BY layoff_count DESC
    """)
    rows = cur.fetchall()

    print(f"本季度共 {len(rows)} 条裁员记录\n")
    print(f"{'代码':<10} {'公司':<12} {'人数':>8} {'比例':>8} {'新闻标题 (前60字符)'}")
    print("-" * 110)

    for row in rows:
        ticker, name, count, pct, note = row
        note_short = note[:60] + "..." if note and len(note) > 60 else (note or "")
        pct_str = f"{pct}%" if pct else "-"
        count_str = f"{count:,}" if count else "-"
        print(f"{ticker:<10} {name:<12} {count_str:>8} {pct_str:>8}  {note_short}")

    # 统计
    print("\n" + "=" * 60)
    print(f"统计：总人数 {sum(r[2] for r in rows if r[2]):,} 人")
    print(f"       超1000人：{sum(1 for r in rows if r[2] and r[2] >= 1000)} 家")
    print(f"       100-1000人：{sum(1 for r in rows if r[2] and 100 <= r[2] < 1000)} 家")
    print(f"       少于100人：{sum(1 for r in rows if r[2] and r[2] < 100)} 家")

conn.close()
