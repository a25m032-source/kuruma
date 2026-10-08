import streamlit as st
import random
import itertools

st.title("🚗 部活 車割自動作成アプリ")

# --- 1. メンバーマスタデータの定義 ---
ALL_MEMBERS = [
    {"name": "空斗", "grade": 4, "is_driver": True, "capacity": 4, "suffix": "さん"},
    {"name": "翔瑛", "grade": 4, "is_driver": True, "capacity": 4, "suffix": "さん"},
    {"name": "馨",   "grade": 3, "is_driver": True, "capacity": 4, "suffix": ""},
    {"name": "拓人", "grade": 3, "is_driver": True, "capacity": 4, "suffix": ""},
    {"name": "丈哉", "grade": 3, "is_driver": False, "suffix": "さん"},
    {"name": "優衣", "grade": 3, "is_driver": False, "suffix": "さん"},
    {"name": "祁答院","grade": 3, "is_driver": False, "suffix": "さん"},
    {"name": "奈緒", "grade": 2, "is_driver": False, "suffix": ""},
    {"name": "菜日", "grade": 2, "is_driver": False, "suffix": ""},
    {"name": "陽太", "grade": 2, "is_driver": False, "suffix": ""},
    {"name": "順瑛", "grade": 2, "is_driver": False, "suffix": ""},
    {"name": "愛子", "grade": 1, "is_driver": False, "suffix": ""},
    {"name": "愛",   "grade": 1, "is_driver": False, "suffix": ""},
    {"name": "憲昭", "grade": 1, "is_driver": False, "suffix": ""},
    {"name": "一樹", "grade": 1, "is_driver": False, "suffix": ""},
    {"name": "孝太朗","grade": 1, "is_driver": False, "suffix": ""},
]

# 過去の同乗ログ（仮）
PAST_PAIRS = {
    tuple(sorted(["空斗", "丈哉"])): 2,
    tuple(sorted(["空斗", "奈緒"])): 1,
}

member_dict = {m["name"]: m for m in ALL_MEMBERS}

# --- 2. スマホ画面：条件入力パート ---
st.subheader("1. 本日の参加者選択")
selected_names = st.multiselect(
    "本日参加するメンバーを選んでください",
    options=[m["name"] for m in ALL_MEMBERS],
    default=[m["name"] for m in ALL_MEMBERS]
)

dep_time = st.text_input("出発時刻", value="16:25発")

# --- 3. 自動生成アルゴリズム ---
def calculate_assignment(active_members):
    drivers = [m for m in active_members if m["is_driver"]]
    passengers = [m for m in active_members if not m["is_driver"]]

    best_score = float("inf")
    best_assignment = None

    for _ in range(1500):
        shuffled = passengers.copy()
        random.shuffle(shuffled)

        current_cars = {d["name"]: [] for d in drivers}
        p_idx = 0
        for d in drivers:
            cap_left = d["capacity"] - 1
            assigned = shuffled[p_idx : p_idx + cap_left]
            current_cars[d["name"]] = [m["name"] for m in assigned]
            p_idx += cap_left

        # スコア評価
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

# セッション状態の保持
if "cars" not in st.session_state:
    st.session_state.cars = None

if st.button("🚗 車割りを自動生成する", type="primary"):
    active_m_info = [m for m in ALL_MEMBERS if m["name"] in selected_names]
    st.session_state.cars = calculate_assignment(active_m_info)

# --- 4. スマホ画面：結果表示と手動微調整 ---
if st.session_state.cars:
    st.subheader("2. 自動生成結果 & 手動微調整")
    
    # 車ごとのメンバー入れ替え
    updated_cars = {}
    for driver, passengers in st.session_state.cars.items():
        st.write(f"**【{driver}カー】**")
        # 多重選択・順番変更用UI
        new_passengers = st.multiselect(
            f"{driver}カーの乗員を調整",
            options=selected_names,
            default=passengers,
            key=f"car_{driver}"
        )
        updated_cars[driver] = new_passengers

    # LINE送信用テキストのリアルタイム更新
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
    
    # テキストエリア表示（ここから全選択してコピー可能）
    st.text_area("以下のテキストをコピーしてLINEに貼り付けてください", value=final_text, height=250)
