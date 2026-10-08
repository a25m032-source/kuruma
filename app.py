import re
import random
import itertools
from urllib.parse import quote

import pandas as pd
import streamlit as st

st.title("🚗 部活 車割自動作成アプリ")

# ==========================================
# 1. Googleスプレッドシート連携設定
# ==========================================
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/172337ady7Lr3pCf5t1Y7iFddDP0G23Yr5_pNmPddkgo/edit?usp=sharing"


def sheet_csv_url(url: str, sheet_name: str) -> str:
    """公開スプレッドシートのシート名指定CSV取得URLを作る"""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("スプレッドシートのURLが正しくありません")
    return (
        f"https://docs.google.com/spreadsheets/d/{m.group(1)}"
        f"/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}"
    )


def to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in ("TRUE", "1", "YES", "○", "〇")


@st.cache_data(ttl=10)
def load_data():
    # membersシート
    df_members = pd.read_csv(sheet_csv_url(SPREADSHEET_URL, "members"), dtype=str)
    members_list = []
    for _, row in df_members.iterrows():
        if pd.isna(row.get("名前")) or not str(row["名前"]).strip():
            continue
        suffix = row.get("敬称")
        members_list.append({
            "name": str(row["名前"]).strip(),
            "grade": int(float(row["学年"])),
            "is_driver": to_bool(row["ドライバー"]),
            "capacity": int(float(row["定員"])) if pd.notna(row.get("定員")) else 0,
            "suffix": "" if pd.isna(suffix) else str(suffix).strip(),
        })

    # historyシート（無くても動くように）
    past_pairs = {}
    try:
        df_history = pd.read_csv(sheet_csv_url(SPREADSHEET_URL, "history"), dtype=str)
        for _, row in df_history.iterrows():
            if pd.isna(row.get("名前1")) or pd.isna(row.get("名前2")):
                continue
            m1 = str(row["名前1"]).strip()
            m2 = str(row["名前2"]).strip()
            cnt = str(row.get("回数", "0")).strip()
            count = int(float(cnt)) if cnt not in ("", "nan") else 0
            past_pairs[tuple(sorted([m1, m2]))] = count
    except Exception:
        pass

    return members_list, past_pairs


try:
    ALL_MEMBERS, PAST_PAIRS = load_data()
    member_dict = {m["name"]: m for m in ALL_MEMBERS}
except Exception as e:
    st.error(
        "スプレッドシートの読み込みに失敗しました。URLやシート名、"
        "公開設定（閲覧者：リンクを知っている全員）を確認してください。"
    )
    st.exception(e)
    st.stop()

if st.button("🔄 スプレッドシートの最新データを再読み込み"):
    st.cache_data.clear()
    st.rerun()

# ==========================================
# 2. 条件入力パート
# ==========================================
st.subheader("1. 本日の参加者選択")
selected_names = st.multiselect(
    "本日参加するメンバーを選んでください",
    options=[m["name"] for m in ALL_MEMBERS],
    default=[m["name"] for m in ALL_MEMBERS],
)

dep_time = st.text_input("出発時刻", value="16:25発")


# ==========================================
# 3. 自動生成アルゴリズム
# ==========================================
def calculate_assignment(active_members):
    drivers = [m for m in active_members if m["is_driver"]]
    passengers = [m for m in active_members if not m["is_driver"]]

    if not drivers:
        return None, "ドライバーが参加者にいません。"

    total_seats = sum(max(d["capacity"] - 1, 0) for d in drivers)
    if total_seats < len(passengers):
        return None, (
            f"席が足りません（同乗者 {len(passengers)}人 / 空席 {total_seats}席）。"
            "ドライバーを増やすか、参加者を減らしてください。"
        )

    best_score = float("inf")
    best_assignment = None

    for _ in range(2000):
        shuffled = passengers.copy()
        random.shuffle(shuffled)

        # 空席のある車のうち、乗員が最も少ない車へ順に割り当て（均等に分散）
        cars = {d["name"]: [] for d in drivers}
        cap = {d["name"]: max(d["capacity"] - 1, 0) for d in drivers}
        for p in shuffled:
            candidates = [n for n in cars if len(cars[n]) < cap[n]]
            min_len = min(len(cars[n]) for n in candidates)
            choice = random.choice([n for n in candidates if len(cars[n]) == min_len])
            cars[choice].append(p["name"])

        penalty = 0
        for d_name, p_list in cars.items():
            all_m = [d_name] + p_list
            for m1, m2 in itertools.combinations(all_m, 2):
                penalty += PAST_PAIRS.get(tuple(sorted([m1, m2])), 0) * 10
            grades = [member_dict[m]["grade"] for m in all_m]
            for g in set(grades):
                if grades.count(g) >= 3:
                    penalty += (grades.count(g) - 2) * 8

        if penalty < best_score:
            best_score = penalty
            best_assignment = cars

    return best_assignment, None


if "cars" not in st.session_state:
    st.session_state.cars = None

if st.button("🚗 車割りを自動生成する", type="primary"):
    active = [m for m in ALL_MEMBERS if m["name"] in selected_names]
    cars, err = calculate_assignment(active)
    # 前回の手動調整の状態を破棄（残るとdefaultが反映されない）
    for k in [k for k in st.session_state if k.startswith("car_")]:
        del st.session_state[k]
    if err:
        st.error(err)
    st.session_state.cars = cars

# ==========================================
# 4. 結果表示 & 手動微調整 & LINE用出力
# ==========================================
if st.session_state.cars:
    st.subheader("2. 自動生成結果 & 手動微調整")

    driver_names = list(st.session_state.cars.keys())
    # ドライバー以外かつ現在参加者のみ選択肢にする
    pass_options = [n for n in selected_names if n not in driver_names]

    updated_cars = {}
    for driver, passengers in st.session_state.cars.items():
        st.write(f"**【{driver}カー】**（定員 {member_dict[driver]['capacity']}人）")
        updated_cars[driver] = st.multiselect(
            f"{driver}カーの乗員を調整",
            options=pass_options,
            default=[p for p in passengers if p in pass_options],
            key=f"car_{driver}",
        )

    # 整合性チェック
    assigned = [p for ps in updated_cars.values() for p in ps]
    dups = {p for p in assigned if assigned.count(p) > 1}
    missing = [p for p in pass_options if p not in assigned]
    if dups:
        st.warning(f"複数の車に重複して乗っている人がいます: {', '.join(sorted(dups))}")
    if missing:
        st.warning(f"どの車にも乗っていない人がいます: {', '.join(missing)}")
    for d, ps in updated_cars.items():
        if len(ps) + 1 > member_dict[d]["capacity"]:
            st.warning(f"{d}カーが定員オーバーです（{len(ps) + 1}/{member_dict[d]['capacity']}人）")

    # LINE投稿用テキスト
    st.subheader("3. LINE投稿用テキスト")
    lines = ["お疲れ様です。", "本日の車割です。", "ご確認よろしくお願いします。\n"]
    for driver, passengers in updated_cars.items():
        lines.append(f"{driver}{member_dict[driver]['suffix']}カー {dep_time}")
        for p in passengers:
            lines.append(f"{p}{member_dict[p]['suffix']}")
        lines.append("")

    st.text_area(
        "以下のテキストをコピーしてLINEに貼り付けてください",
        value="\n".join(lines),
        height=200,
        key="line_text",
    )

    # 過去履歴追加用テキスト
    st.subheader("4. 過去履歴への自動加算")
    updated_pairs = PAST_PAIRS.copy()
    for driver, passengers in updated_cars.items():
        for m1, m2 in itertools.combinations([driver] + passengers, 2):
            pair = tuple(sorted([m1, m2]))
            updated_pairs[pair] = updated_pairs.get(pair, 0) + 1

    tsv_lines = ["名前1\t名前2\t回数"]
    for (m1, m2), count in sorted(updated_pairs.items()):
        tsv_lines.append(f"{m1}\t{m2}\t{count}")

    st.caption(
        "今回の車割りを反映した最新の履歴一覧です。"
        "必要に応じてスプレッドシートの 'history' シート全体に上書き貼り付けしてください。"
    )
    st.text_area(
        "最新の history シート用データ（全選択して上書き用）",
        value="\n".join(tsv_lines),
        height=200,
        key="history_text",
    )
