import streamlit as st
import pandas as pd
import gspread
import random
import itertools

st.title("🚗 部活 車割自動作成アプリ")

# ==========================================
# 1. Googleスプレッドシート連携設定
# ==========================================
# ★ご自身のスプレッドシートURLをここに貼り付けてください
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/172337ady7Lr3pCf5t1Y7iFddDP0G23Yr5_pNmPddkgo/edit?usp=sharing"

@st.cache_data(ttl=10) # キャッシュ10秒
def load_data():
    gc = gspread.public_authorize(SPREADSHEET_URL)
    sh = gc.open_by_url(SPREADSHEET_URL)
    
    # membersシートの読み込み
    ws_members = sh.worksheet("members")
    df_members = pd.DataFrame(ws_members.get_all_records())
    
    members_list = []
    for _, row in df_members.iterrows():
        members_list.append({
            "name": str(row["名前"]).strip(),
            "grade": int(row["学年"]),
            "is_driver": bool(row["ドライバー"]) if isinstance(row["ドライバー"], bool) else (str(row["ドライバー"]).upper() == "TRUE"),
            "capacity": int(row["定員"]),
            "suffix": str(row["敬称"]).strip() if pd.notna(row["敬称"]) and str(row["敬称"]).strip() != "nan" else ""
        })

    # historyシートの読み込み
    past_pairs = {}
    try:
        ws_history = sh.worksheet("history")
        df_history = pd.DataFrame(ws_history.get_all_records())
        for _, row in df_history.iterrows():
            m1 = str(row["名前1"]).strip()
            m2 = str(row["名前2"]).strip()
            count = int(row["回数"]) if str(row["回数"]).isdigit() else 0
            pair = tuple(sorted([m1, m2]))
            past_pairs[pair] = count
    except Exception:
        pass

    return members_list, past_pairs

try:
    ALL_MEMBERS, PAST_PAIRS = load_data()
    member_dict = {m["name"]: m for m in ALL_MEMBERS}
except Exception as e:
    st.error("スプレッドシートの読み込みに失敗しました。URLやシート名、公開設定（閲覧者：リンクを知っている全員）を確認してください。")
    st.stop()

if st.button("🔄 スプレッドシートの最新データを再読み込み"):
    st.cache_data.clear()
    st.rerun()

# ==========================================
# 2. スマホ画面：条件入力パート
# ==========================================
st.subheader("1. 本日の参加者選択")
selected_names = st.multiselect(
    "本日参加するメンバーを選んでください",
    options=[m["name"] for m in ALL_MEMBERS],
    default=[m["name"] for m in ALL_MEMBERS]
)

dep_time = st.text_input("出発時刻", value="16:25発")

# ==========================================
# 3. 自動生成アルゴリズム
# ==========================================
def calculate_assignment(active_members):
    drivers = [m for m in active_members if m["is_driver"]]
    passengers = [m for m in active_members if not m["is_driver"]]

    best_score = float("inf")
    best_assignment = None

    for _ in range(2000):
        shuffled = passengers.copy()
        random.shuffle(shuffled)

        current_cars = {d["name"]: [] for d in drivers}
        p_idx = 0
        for d in drivers:
            cap_left = d["capacity"] - 1
            assigned = shuffled[p_idx : p_idx + cap_left]
            current_cars[d["name"]] = [m["name"] for m in assigned]
            p_idx += cap_left

        penalty = 0
        for d_name, p_list in current_cars.items():
            all_m = [d_name] + p_list
            for m1, m2 in itertools.combinations(all_m, 2):
                penalty += PAST_PAIRS.get(tuple(sorted([m1, m2])), 0) * 10
            grades = [member_dict[m]["grade"] for m in all_m if m in member_dict]
            for g in set(grades):
                if grades.count(g) >= 3:
                    penalty += (grades.count(g) - 2) * 8

        if penalty < best_score:
            best_score = penalty
            best_assignment = current_cars

    return best_assignment

if "cars" not in st.session_state:
    st.session_state.cars = None

if st.button("🚗 車割りを自動生成する", type="primary"):
    active_m_info = [m for m in ALL_MEMBERS if m["name"] in selected_names]
    st.session_state.cars = calculate_assignment(active_m_info)

# ==========================================
# 4. 結果表示 & 手動微調整 & LINE用出力
# ==========================================
if st.session_state.cars:
    st.subheader("2. 自動生成結果 & 手動微調整")
    
    updated_cars = {}
    for driver, passengers in st.session_state.cars.items():
        st.write(f"**【{driver}カー】**")
        new_passengers = st.multiselect(
            f"{driver}カーの乗員を調整",
            options=selected_names,
            default=passengers,
            key=f"car_{driver}"
        )
        updated_cars[driver] = new_passengers

    # LINE投稿用テキスト
    st.subheader("3. LINE投稿用テキスト")
    lines = ["お疲れ様です。", "本日の車割です。", "ご確認よろしくお願いします。\n"]
    for driver, passengers in updated_cars.items():
        d_info = member_dict[driver]
        d_suf = d_info['suffix'] if d_info['suffix'] else ""
        lines.append(f"{driver}{d_suf}カー {dep_time}")
        for p in passengers:
            p_info = member_dict[p]
            p_suf = p_info['suffix'] if p_info['suffix'] else ""
            lines.append(f"{p}{p_suf}")
        lines.append("")

    final_text = "\n".join(lines)
    st.text_area("以下のテキストをコピーしてLINEに貼り付けてください", value=final_text, height=200)

    # 過去履歴追加用テキストの自動生成
    st.subheader("4. 過去履歴への自動加算")
    updated_pairs = PAST_PAIRS.copy()
    for driver, passengers in updated_cars.items():
        all_members = [driver] + passengers
        for m1, m2 in itertools.combinations(all_members, 2):
            pair = tuple(sorted([m1, m2]))
            updated_pairs[pair] = updated_pairs.get(pair, 0) + 1

    tsv_lines = ["名前1\t名前2\t回数"]
    for (m1, m2), count in sorted(updated_pairs.items()):
        tsv_lines.append(f"{m1}\t{m2}\t{count}")
    
    latest_history_text = "\n".join(tsv_lines)
    st.caption("今回の車割りを反映した最新の履歴一覧です。必要に応じてスプレッドシートの 'history' シート全体に上書き貼り付けしてください。")
    st.text_area("最新の history シート用データ（全選択して上書き用）", value=latest_history_text, height=150)
    latest_history_text = "\n".join(tsv_lines)
    
    st.caption("今回の車割りを反映した最新の履歴一覧です。必要に応じてスプレッドシートの 'history' シート全体に上書き貼り付けしてください。")
    st.text_area("最新の history シート用データ（全選択して上書き用）", value=latest_history_text, height=200)
