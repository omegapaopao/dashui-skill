#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大水理论 · 抽卡 / 任务 / 记账 / 周报 / 通告卡（可选工具）

    py -3.12 dashui.py draw --level 3 --scene code
    py -3.12 dashui.py daily
    py -3.12 dashui.py checkin
    py -3.12 dashui.py log --event drank --ml 500
    py -3.12 dashui.py log --event refused --note "我刚喝过"
    py -3.12 dashui.py report --days 7
    py -3.12 dashui.py style --set instructor
    py -3.12 dashui.py poster
    py -3.12 dashui.py status

状态文件默认在 %USERPROFILE%\\.dashui\\state.json，可用 DASHUI_HOME 覆盖。
"""

from __future__ import annotations

import argparse
import hashlib
import html as htmlesc
import json
import os
import random
import sys
from datetime import date, datetime, timedelta
from string import Template

HERE = os.path.dirname(os.path.abspath(__file__))
LINES_PATH = os.path.join(HERE, "lines.json")
MISSIONS_PATH = os.path.join(HERE, "missions.json")
QUOTES_PATH = os.path.join(HERE, "quotes.json")
HOME = os.environ.get("DASHUI_HOME") or os.path.join(os.path.expanduser("~"), ".dashui")
STATE_PATH = os.path.join(HOME, "state.json")

EVENT_LINES = {
    "drank": "已记录：{ml} 毫升。你的肾刚收到一笔回款。",
    "refused": "已记录：拒绝。拒绝是数据，不是结论。",
    "closed": "水阀已关。本所停止观测。",
    "opened": "水阀已开。观测恢复。",
}

STYLES = {
    "academic": {"label": "学术 · 陆一杯", "sample": "数据不骗人，骗人的是你没喝水。"},
    "service": {"label": "客服 · 小水", "sample": "亲，这边查询到您今天还没有饮水记录呢。"},
    "instructor": {"label": "教官 · 老雷", "sample": "停。手离开键盘。拿瓶。拧开。喝。三口。完毕。"},
    "zen": {"label": "禅宗 · 无水", "sample": "你端起杯子时，水已经在喝你。那还喝吗？喝。"},
    "classical": {"label": "文言 · 水部侍郎", "sample": "足下晨起至今，未沾滴露。速取巨瓶，仰而尽之。"},
}

TITLES = [
    (30, "传说级大水人"),
    (14, "首席饮水官"),
    (7, "骆驼骑士"),
    (3, "大水人"),
    (1, "初级大水人"),
    (0, "见习大水人"),
]

TAG_NOTES = {
    "环境": "环境不改，行为不改。瓶子在视线里，喝水才会发生。",
    "清瓶": "清瓶率是本所唯一的硬指标。见底，才算数。",
    "采购": "先有瓶，后有水。别在渴的时候才想起下单。",
    "记录": "没有记录，等于没喝。本所只认数字。",
    "社交": "一个人喝是自律，两个人喝是文化。",
    "节制": "今天的目标不是多喝，是只喝对的。",
    "仪式": "仪式不是迷信，是给动作一个开始的理由。",
    "运动": "先动，再喝。顺序反了，你只会想躺下。",
    "睡眠": "夜里你的肾不休息。睡前那 200 毫升，是给它的加班费。",
    "工作": "会议不会因为你喝水而变短，但你会因为喝水而清醒。",
}


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return date.today().isoformat()


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_lines() -> list:
    data = load_json(LINES_PATH)
    if not isinstance(data, list) or not data:
        raise SystemExit("lines.json 为空或格式不对")
    return data


def load_missions() -> list:
    data = load_json(MISSIONS_PATH)
    if not isinstance(data, list) or not data:
        raise SystemExit("missions.json 为空或格式不对")
    return data


def load_quotes() -> list:
    data = load_json(QUOTES_PATH)
    if not isinstance(data, list) or not data:
        raise SystemExit("quotes.json 为空或格式不对")
    return data


def load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            raise ValueError("state is not a dict")
    except Exception:
        state = {}
    state.setdefault("created", now_iso())
    state.setdefault("events", [])
    state.setdefault("used", [])
    state.setdefault("closed", False)
    state.setdefault("style", "academic")
    state.setdefault("missions", {})
    state.setdefault("streak", 0)
    state.setdefault("best_streak", 0)
    state.setdefault("last_checkin", "")
    state["version"] = 2
    return state


def save_state(state: dict) -> None:
    os.makedirs(HOME, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def title_for(streak: int) -> str:
    for need, name in TITLES:
        if streak >= need:
            return name
    return "见习大水人"


def next_title(streak: int):
    for need, name in reversed(TITLES):
        if streak < need:
            return need, name
    return None


def ensure_mission(state: dict, day: str) -> dict:
    mission = state["missions"].get(day)
    if isinstance(mission, dict):
        return mission
    missions = load_missions()
    index = int(hashlib.md5(day.encode("utf-8")).hexdigest(), 16) % len(missions)
    src = missions[index]
    mission = {
        "id": src["id"],
        "tag": src.get("tag", ""),
        "text": src["text"],
        "done": False,
        "done_at": "",
    }
    state["missions"][day] = mission
    keys = sorted(state["missions"])
    for old in keys[:-180]:
        del state["missions"][old]
    return mission


def day_ml(state: dict, day: str) -> int:
    total = 0
    for event in state["events"]:
        if event.get("event") == "drank" and str(event.get("t", ""))[:10] == day:
            total += int(event.get("ml") or 0)
    return total


def week_ml(state: dict, end: date, days: int = 7) -> int:
    start = (end - timedelta(days=days - 1)).isoformat()
    total = 0
    for event in state["events"]:
        if event.get("event") != "drank":
            continue
        stamp = str(event.get("t", ""))[:10]
        if start <= stamp <= end.isoformat():
            total += int(event.get("ml") or 0)
    return total


def cmd_draw(args: argparse.Namespace) -> None:
    lines = load_lines()
    state = load_state()

    pool = [l for l in lines if args.scene is None or l.get("scene") == args.scene]
    if args.level is not None:
        leveled = [l for l in pool if l.get("level") == args.level]
        if leveled:
            pool = leveled
    if not pool:
        pool = lines

    recent = set(state["used"][-10:])
    fresh = [l for l in pool if l.get("id") not in recent]
    if fresh:
        pool = fresh
    else:
        # 池子太小、全都用过了：直接取最久没出现的那条，保证严格轮换
        last_pos = {}
        for i, lid in enumerate(state["used"]):
            last_pos[lid] = i
        ordered = sorted(pool, key=lambda l: last_pos.get(l.get("id"), -1))
        pool = ordered[:1]

    line = random.SystemRandom().choice(pool)
    state["used"].append(line["id"])
    state["used"] = state["used"][-60:]
    save_state(state)

    if args.plain:
        print(line["text"])
    else:
        print(f"【L{line['level']} · {line['scene']}】{line['text']}")


def cmd_log(args: argparse.Namespace) -> None:
    state = load_state()
    ml = max(0, int(args.ml or 0))
    note = (args.note or "").strip()
    event = {"t": now_iso(), "event": args.event, "ml": ml}
    if note:
        event["note"] = note
    state["events"].append(event)
    state["events"] = state["events"][-300:]
    if args.event == "closed":
        state["closed"] = True
    elif args.event == "opened":
        state["closed"] = False
    save_state(state)
    print(EVENT_LINES[args.event].format(ml=ml))


def cmd_daily(args: argparse.Namespace) -> None:
    state = load_state()
    day = today_str()
    mission = ensure_mission(state, day)
    save_state(state)

    streak = int(state.get("streak", 0))
    print(f"【今日大水任务 · {day}】")
    print(f"[{mission['tag']}] {mission['text']}")
    print(f"状态：{'已完成' if mission['done'] else '未完成'}")
    print(f"连续：{streak} 天 · 称号：{title_for(streak)}")
    if not mission["done"]:
        print("完成后：dashui.py checkin")
    note = TAG_NOTES.get(mission["tag"], "先做，再想。")
    print(f"\n本所批注：{note}")


def cmd_checkin(args: argparse.Namespace) -> None:
    state = load_state()
    day = today_str()
    mission = ensure_mission(state, day)
    if mission["done"]:
        print("今天已经打过卡了。重复打卡不加连续，本所不搞通胀。")
        return

    previous_streak = int(state.get("streak", 0))
    previous_title = title_for(previous_streak)
    mission["done"] = True
    mission["done_at"] = now_iso()

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if state.get("last_checkin") == yesterday:
        state["streak"] = int(state.get("streak", 0)) + 1
    else:
        state["streak"] = 1
    state["last_checkin"] = day
    state["best_streak"] = max(int(state.get("best_streak", 0)), int(state["streak"]))
    state["events"].append(
        {"t": now_iso(), "event": "checkin", "ml": 0, "mission": mission["id"]}
    )
    state["events"] = state["events"][-300:]
    save_state(state)

    streak = int(state["streak"])
    print(f"已打卡：{day}")
    print(f"连续 {streak} 天 · 称号：{title_for(streak)}")
    upgraded = title_for(streak)
    if upgraded != previous_title:
        if streak > previous_streak:
            print(f"称号升级：{previous_title} → {upgraded}")
        else:
            print(f"称号重置：{previous_title} → {upgraded}（连续中断，重新开始）")
    nxt = next_title(streak)
    if nxt:
        print(f"距「{nxt[1]}」还差 {nxt[0] - streak} 天。")


def cmd_status(args: argparse.Namespace) -> None:
    state = load_state()
    day = today_str()
    mission = ensure_mission(state, day)
    save_state(state)

    ml = day_ml(state, day)
    drinks = [
        e for e in state["events"]
        if e.get("event") == "drank" and str(e.get("t", ""))[:10] == day
    ]
    last = next((e for e in reversed(state["events"]) if e.get("event") == "drank"), None)
    streak = int(state.get("streak", 0))

    if ml <= 0:
        verdict = "今日尚无摄入记录。你正在以每小时约 30 毫升的速度变成一件文物。"
    elif ml < 1500:
        verdict = f"今日 {ml} 毫升，离参考量还差 {1500 - ml} 毫升。少量多次，别攒到晚上。"
    else:
        verdict = "今日达标。本所授予你「大水人」临时称号，有效期到明天零点。"

    print("大水理论研究所 · 受试者档案")
    print("─" * 34)
    print(f"协议状态  ：{'已关阀' if state.get('closed') else '生效中'}")
    print(f"当前风格  ：{STYLES.get(state.get('style'), STYLES['academic'])['label']}")
    print(f"建档日期  ：{str(state.get('created', ''))[:10]}")
    print(f"累计抽卡  ：{len(state.get('used', []))} 次")
    print(f"累计记录  ：{len(state.get('events', []))} 条")
    print(f"今日饮水  ：{len(drinks)} 次 / {ml} ml")
    print(f"今日任务  ：[{mission['tag']}] {mission['text']}")
    print(f"            {'已完成' if mission['done'] else '未完成'}")
    print(f"称号连续  ：{title_for(streak)} · {streak} 天（最佳 {state.get('best_streak', 0)} 天）")
    if last:
        print(f"最近饮水  ：{last.get('t')}（{hours_since(str(last.get('t')))}）")
    else:
        print("最近饮水  ：无记录")
    print("─" * 34)
    print(f"本所评语：{verdict}")


def hours_since(ts: str) -> str:
    try:
        then = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return "未知"
    delta = datetime.now() - then
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)} 分钟前"
    if hours < 24:
        return f"{hours:.1f} 小时前"
    return f"{hours / 24:.1f} 天前"


def cmd_report(args: argparse.Namespace) -> None:
    state = load_state()
    days = max(1, int(args.days or 7))
    end = date.today()
    start = end - timedelta(days=days - 1)
    start_s, end_s = start.isoformat(), end.isoformat()

    def within(event: dict) -> bool:
        stamp = str(event.get("t", ""))[:10]
        return start_s <= stamp <= end_s

    events = [e for e in state["events"] if within(e)]
    drinks = [e for e in events if e.get("event") == "drank"]
    refusals = [e for e in events if e.get("event") == "refused"]
    checkins = [e for e in events if e.get("event") == "checkin"]

    per_day = {}
    for event in drinks:
        day = str(event.get("t", ""))[:10]
        per_day[day] = per_day.get(day, 0) + int(event.get("ml") or 0)
    total = sum(per_day.values())
    avg = total // days
    hit_days = sum(1 for v in per_day.values() if v >= 1500)
    best_day = max(per_day.items(), key=lambda kv: kv[1]) if per_day else ("—", 0)

    notes = [str(e.get("note", "")).strip() for e in refusals if e.get("note")]
    excuse = notes[-1] if notes else "本周期没有留下借口。可疑。"

    if avg >= 1500:
        verdict = "达标。建议你写一篇方法论，标题就叫《我只是每天喝 1.5L》。"
    elif avg >= 800:
        verdict = "有进步，但离「大水人」还有一段水位。"
    elif avg > 0:
        verdict = "摄入存在，但不足以支撑一个理论。"
    else:
        verdict = "本周期没有饮水记录。你是在用行为艺术反对本所吗？"

    print(f"【大水周报 · {start_s} ~ {end_s}】")
    print(f"饮水次数：{len(drinks)} 次")
    print(f"饮水总量：{total} ml")
    print(f"日均    ：{avg} ml")
    print(f"达标天数：{hit_days} / {days}（≥1500 ml）")
    print(f"最佳单日：{best_day[1]} ml")
    print(f"任务打卡：{len(checkins)} 次")
    print(f"拒绝记录：{len(refusals)} 次")
    print(f"当前称号：{title_for(int(state.get('streak', 0)))} · 连续 {state.get('streak', 0)} 天（最佳 {state.get('best_streak', 0)} 天）")
    print(f"本周期最佳借口：{excuse}")
    print(f"结论：{verdict}")


def cmd_style(args: argparse.Namespace) -> None:
    state = load_state()
    if args.list:
        print("可用风格：")
        for key, info in STYLES.items():
            print(f"  {key:<10} {info['label']}")
        return
    if args.set:
        state["style"] = args.set
        save_state(state)
    key = state.get("style", "academic")
    info = STYLES.get(key, STYLES["academic"])
    print(f"当前风格：{info['label']}")
    print(f"示例    ：{info['sample']}")
    if not args.set:
        print("切换    ：dashui.py style --set <academic|service|instructor|zen|classical>")


POSTER_TMPL = Template(r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>大水通告 · $day</title>
<style>
  @page { size: 1080px 1440px; margin: 0; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1080px; height: 1440px; }
  body {
    background: #F2EDE3;
    color: #14110D;
    font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "SimSun", serif;
    overflow: hidden;
    position: relative;
  }
  .wm {
    position: absolute; right: -140px; bottom: -300px;
    font-size: 980px; line-height: 1; font-weight: 700;
    color: transparent; -webkit-text-stroke: 2px rgba(20,17,13,.06);
    z-index: 0; user-select: none;
  }
  main {
    position: relative; z-index: 1;
    padding: 62px 72px 52px;
    height: 100%;
    display: flex; flex-direction: column;
  }
  header { display: flex; justify-content: space-between; align-items: flex-start; }
  .brand { font-size: 20px; font-weight: 700; letter-spacing: 2px; }
  .brand small { display: block; margin-top: 6px; font-family: "Consolas", monospace; font-size: 11px; letter-spacing: 3px; color: #6B6459; font-weight: 400; }
  .no { text-align: right; font-family: "Consolas", monospace; font-size: 12px; letter-spacing: 2px; color: #6B6459; }
  .no strong { display: block; margin-top: 8px; font-family: "SimSun", serif; font-size: 26px; letter-spacing: 1px; color: #14110D; }
  .rule { height: 2px; background: #14110D; margin-top: 28px; }
  .label { margin-top: 52px; font-family: "Consolas", monospace; font-size: 13px; letter-spacing: 6px; color: #6B6459; }
  .hero { display: flex; align-items: baseline; gap: 14px; margin-top: 2px; }
  .big { font-family: "Times New Roman", "SimSun", serif; font-size: 206px; line-height: .95; font-weight: 700; letter-spacing: -6px; font-variant-numeric: tabular-nums; }
  .unit { font-size: 30px; color: #6B6459; letter-spacing: 1px; }
  .bar { margin-top: 24px; height: 16px; background: #DCD2C2; position: relative; }
  .fill { height: 100%; background: #12507A; width: $pct%; }
  .scale { display: flex; justify-content: space-between; margin-top: 8px; font-family: "Consolas", monospace; font-size: 12px; color: #6B6459; }
  .stats { display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 28px; margin-top: 40px; padding: 24px 0; border-top: 1px solid #BDB3A2; border-bottom: 1px solid #BDB3A2; }
  .stat .k { font-family: "Consolas", monospace; font-size: 11px; letter-spacing: 3px; color: #6B6459; }
  .stat .v { margin-top: 8px; font-size: 34px; font-weight: 700; letter-spacing: 1px; }
  .stat .s { margin-top: 4px; font-size: 14px; color: #6B6459; }
  .mission { margin-top: 32px; padding-left: 22px; border-left: 6px solid #12507A; }
  .mission .k { font-family: "Consolas", monospace; font-size: 11px; letter-spacing: 3px; color: #6B6459; }
  .mission .tag { display: inline-block; margin-left: 10px; padding: 2px 8px; background: #12507A; color: #F2EDE3; font-family: "Microsoft YaHei", sans-serif; font-size: 12px; letter-spacing: 1px; vertical-align: 2px; }
  .mission .t { margin-top: 12px; font-size: 29px; line-height: 1.5; font-weight: 600; }
  .mission .ok { margin-top: 10px; font-family: "Consolas", monospace; font-size: 13px; letter-spacing: 2px; color: #12507A; }
  .mission .ok.todo { color: #8A5A1F; }
  .trend { margin-top: 28px; }
  .trend .k { font-family: "Consolas", monospace; font-size: 11px; letter-spacing: 3px; color: #6B6459; }
  .bars { display: flex; gap: 16px; align-items: flex-end; margin-top: 14px; }
  .bcol { flex: 1; }
  .bval { font-family: "Consolas", monospace; font-size: 11px; color: #6B6459; text-align: center; margin-bottom: 6px; }
  .btrack { height: 84px; display: flex; align-items: flex-end; border-bottom: 1px solid #CFC4B2; }
  .bfill { width: 100%; background: #C3B7A4; min-height: 2px; }
  .bcol.today .bfill { background: #12507A; }
  .blab { margin-top: 7px; text-align: center; font-size: 12px; color: #6B6459; }
  .bcol.today .blab { color: #12507A; font-weight: 700; }
  .verdict { margin-top: 24px; display: flex; gap: 18px; align-items: baseline; border-top: 1px solid #D6CCBC; padding-top: 14px; }
  .verdict .k { font-family: "Consolas", monospace; font-size: 11px; letter-spacing: 3px; color: #6B6459; white-space: nowrap; }
  .verdict .v { font-size: 21px; line-height: 1.5; }
  .quote { margin-top: auto; padding-top: 26px; }
  .quote .mark { font-size: 52px; line-height: 1; color: #12507A; }
  .quote .q { font-size: 40px; line-height: 1.5; font-weight: 600; letter-spacing: 1px; }
  .quote .by { margin-top: 12px; font-family: "Consolas", monospace; font-size: 12px; letter-spacing: 3px; color: #6B6459; text-align: right; }
  footer { margin-top: 26px; padding-top: 16px; border-top: 1px solid #BDB3A2; display: flex; justify-content: space-between; font-family: "Consolas", "Microsoft YaHei", monospace; font-size: 11px; letter-spacing: 1px; color: #6B6459; }
</style>
</head>
<body>
  <div class="wm">水</div>
  <main>
    <header>
      <div class="brand">大水理论研究所<small>INSTITUTE OF DASHUI STUDIES</small></div>
      <div class="no">DAILY HYDRATION BULLETIN<strong>$day</strong></div>
    </header>
    <div class="rule"></div>
    <div class="label">今日水位 / TODAY</div>
    <div class="hero"><span class="big">$ml</span><span class="unit">/ 1500 ml</span></div>
    <div class="bar"><div class="fill"></div></div>
    <div class="scale"><span>0</span><span>750</span><span>1500 ml</span></div>
    <div class="stats">
      <div class="stat"><div class="k">称号 / TITLE</div><div class="v">$title</div><div class="s">当前风格：$style_label</div></div>
      <div class="stat"><div class="k">连续 / STREAK</div><div class="v">$streak 天</div><div class="s">最佳 $best 天</div></div>
      <div class="stat"><div class="k">本周 / 7 DAYS</div><div class="v">$week_ml ml</div><div class="s">日均 $week_avg ml</div></div>
    </div>
    <div class="mission">
      <div class="k">今日任务 / MISSION<span class="tag">$mission_tag</span></div>
      <div class="t">$mission_text</div>
      <div class="ok $mission_class">$mission_status</div>
    </div>
    <div class="trend">
      <div class="k">本周水位 / LAST 7 DAYS</div>
      <div class="bars">$bars</div>
    </div>
    <div class="verdict">
      <div class="k">本所判词 / VERDICT</div>
      <div class="v">$verdict</div>
    </div>
    <div class="quote">
      <div class="mark">「</div>
      <div class="q">$quote</div>
      <div class="by">—— $quote_by</div>
    </div>
    <footer>
      <span>本卡由大水理论研究所签发 · 仅供娱乐 · 不具有任何医学效力</span>
      <span>$generated</span>
    </footer>
  </main>
</body>
</html>
""")


def cmd_poster(args: argparse.Namespace) -> None:
    state = load_state()
    day = today_str()
    mission = ensure_mission(state, day)
    save_state(state)

    ml = day_ml(state, day)
    week = week_ml(state, date.today(), 7)
    streak = int(state.get("streak", 0))
    pct = max(0, min(100, round(ml * 100 / 1500)))
    quote = random.Random(day).choice(load_quotes())
    style_label = STYLES.get(state.get("style"), STYLES["academic"])["label"]

    if ml <= 0:
        verdict = "今日尚无摄入记录。"
    elif ml < 1500:
        verdict = f"今日 {ml} ml，离参考量还差 {1500 - ml} ml。少量多次。"
    else:
        verdict = "今日达标。临时称号：大水人，有效期到明天零点。"

    today = date.today()
    values = [(today - timedelta(days=i), 0) for i in range(6, -1, -1)]
    values = [(d, day_ml(state, d.isoformat())) for d, _ in values]
    scale = max(1500, max((v for _, v in values), default=0))
    bars = []
    for i, (d, v) in enumerate(values):
        height = max(1, round(v * 100 / scale))
        cls = "bcol today" if i == 6 else "bcol"
        label = "一二三四五六日"[d.weekday()]
        bars.append(
            f'<div class="{cls}"><div class="bval">{v}</div>'
            f'<div class="btrack"><div class="bfill" style="height:{height}%"></div></div>'
            f'<div class="blab">{label}</div></div>'
        )

    content = POSTER_TMPL.substitute(
        day=day.replace("-", "."),
        ml=str(ml),
        pct=str(pct),
        title=htmlesc.escape(title_for(streak)),
        style_label=htmlesc.escape(style_label),
        streak=str(streak),
        best=str(state.get("best_streak", 0)),
        week_ml=str(week),
        week_avg=str(week // 7),
        mission_tag=htmlesc.escape(mission.get("tag", "")),
        mission_text=htmlesc.escape(mission.get("text", "")),
        mission_status="✓ 已完成" if mission.get("done") else "○ 未完成",
        mission_class="done" if mission.get("done") else "todo",
        bars="".join(bars),
        verdict=htmlesc.escape(verdict),
        quote=htmlesc.escape(quote["text"]),
        quote_by=htmlesc.escape(quote["by"]),
        generated=now_iso(),
    )

    if args.stdout:
        print(content)
        return

    out = args.out or os.path.join(HOME, "posters", f"dashui-{day}.html")
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"通告卡已生成：{out}")
    print("用浏览器打开，按 1080×1440 截图即可发朋友圈。")
    print("内容：今日水位、称号、连续天数、今日任务、本周日均、一句箴言。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashui",
        description="大水理论 · 抽卡 / 任务 / 记账 / 周报 / 通告卡（娱乐向，不是医疗工具）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    draw = sub.add_parser("draw", help="抽一条钩子")
    draw.add_argument("--level", type=int, choices=range(1, 6), help="水位 L1–L5")
    draw.add_argument("--scene", help="场景：code/writing/video/study/work/...")
    draw.add_argument("--plain", action="store_true", help="只输出正文，便于粘贴")
    draw.set_defaults(func=cmd_draw)

    log = sub.add_parser("log", help="记一笔")
    log.add_argument("--event", required=True, choices=list(EVENT_LINES))
    log.add_argument("--ml", type=int, default=0)
    log.add_argument("--note", default="", help="借口原文，周报会引用")
    log.set_defaults(func=cmd_log)

    daily = sub.add_parser("daily", help="领取今日任务")
    daily.set_defaults(func=cmd_daily)

    checkin = sub.add_parser("checkin", help="完成今日任务并打卡")
    checkin.set_defaults(func=cmd_checkin)

    report = sub.add_parser("report", help="生成周报")
    report.add_argument("--days", type=int, default=7)
    report.set_defaults(func=cmd_report)

    style = sub.add_parser("style", help="切换人格风格")
    style.add_argument("--set", choices=list(STYLES))
    style.add_argument("--list", action="store_true")
    style.set_defaults(func=cmd_style)

    poster = sub.add_parser("poster", help="生成大水通告卡")
    poster.add_argument("--out", help="输出 HTML 路径")
    poster.add_argument("--stdout", action="store_true", help="直接打印 HTML")
    poster.set_defaults(func=cmd_poster)

    status = sub.add_parser("status", help="查看档案")
    status.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    _utf8()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
