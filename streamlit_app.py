# app.py
import streamlit as st
import yaml
import pandas as pd
from openai import OpenAI
import re

# ----------------- SETUP -----------------
api_key = st.secrets.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

TOTAL_BUDGET = 260


# ----------------- HELPERS -----------------
@st.cache_data
def load_cheat_sheet() -> dict:
    """Parse cheat_sheet.md into a structured dict by position."""
    cheat_sheet = {"QB": [], "RB": [], "WR": [], "TE": []}
    current_position = None

    with open("cheat_sheet.md", "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue

            if line.startswith("Top QB"):
                current_position = "QB"; continue
            elif line.startswith("Top RB"):
                current_position = "RB"; continue
            elif line.startswith("Top WR"):
                current_position = "WR"; continue
            elif line.startswith("TOP TE"):
                current_position = "TE"; continue

            if current_position:
                match = re.match(r"^\d+\.\s+(.+?)\s+\((.+?)\)\s+—\s+\$(\d+)", line)
                if match:
                    name, team, cost = match.groups()
                    cheat_sheet[current_position].append({
                        "name": name.strip(),
                        "team": team.strip(),
                        "cost": int(cost),
                    })

    return cheat_sheet


def open_rosters():
    with open("rosters.yml", "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def get_remaining_budgets(data: dict, total_budget: int = 260) -> dict:
    remaining = {}
    for team_name, roster in data.items():
        spent = 0
        for slot, info in roster.items():
            if isinstance(info, dict):
                spent += info.get("cost") or 0   # 👈 fix: ensures None becomes 0
        remaining[team_name] = total_budget - spent
    return remaining


def roster_to_df(team_roster: dict):
    rows = []
    for slot, info in team_roster.items():
        if isinstance(info, dict):
            rows.append({"Slot": slot, "Player": info.get("player", ""), "Cost": info.get("cost", 0)})
        else:
            rows.append({"Slot": slot, "Player": str(info), "Cost": 0})
    return pd.DataFrame(rows)


def rosters_summary(rosters: dict) -> str:
    """Return a compressed roster summary string."""
    summary = []
    for team, slots in rosters.items():
        players = [
            f"{info['player']} (${info['cost']})"
            for info in slots.values()
            if isinstance(info, dict) and info.get("player")
        ]
        summary.append(f"{team}: {', '.join(players) if players else 'empty'}")
    return "\n".join(summary)


def available_players(cheat_sheet: dict, rosters: dict) -> str:
    """Return cheat sheet players excluding already drafted ones."""
    drafted = {
        info["player"]
        for team in rosters.values()
        for info in team.values()
        if isinstance(info, dict) and info.get("player")
    }

    filtered = []
    for pos, players in cheat_sheet.items():
        remaining = [p for p in players if p["name"] not in drafted]
        if remaining:
            top = remaining[:15]  # trim to top 10 per position
            filtered.append(f"\nTop {pos} still available:\n" +
                            ", ".join([f"{p['name']} (${p['cost']})" for p in top]))
    return "\n".join(filtered)


def build_background_info(rosters: dict, strategy: str) -> str:
    cheat_sheet = load_cheat_sheet()
    return f"""
This is a 12-team, $260 auction league budget. 2 starting QBs, 1 extra WR/RB/TE flex. Full PPR.
Draft strategy: {strategy}

Drafted rosters:
{rosters_summary(rosters)}

Available players:
{available_players(cheat_sheet, rosters)}

Note: once a player is drafted on a team, they cannot be drafted again.
"""


def who_should_i_nominate(background_info: str, user_team: str, remaining_budget: int):
    prompt = f"""
Review {user_team}'s current roster and other teams to determine who they should nominate.
Always return:
- A short intro (1–2 sentences)
- Bullet points with 3–5 actionable sentences
"""
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""{background_info}\n\n{prompt}
        {user_team} has a remaining budget of {remaining_budget}.
        """,
    )
    return response.output_text


def should_i_bid(background_info: str, user_team: str, other_team: str, player: str, remaining_budget: int):
    prompt = f"""
Should {user_team} bid on this player nominated by {other_team}?
Always return:
- Direct yes/no recommendation up front
- Bullet points with 3–5 sentences
"""
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""{background_info}\n\n{prompt}
        Team {other_team} nominated {player}.
        {user_team} has {remaining_budget} left.
        """,
    )
    return response.output_text


# ----------------- STREAMLIT APP -----------------
st.title("🏈 Bux AI: Fantasy Draft Assistant")

rosters = open_rosters()
remaining_budget = get_remaining_budgets(rosters)

# User inputs
user_team = st.selectbox("Which team are you?", list(rosters.keys()))
draft_strategy = st.text_area("✍️ Enter Your Draft Strategy",
                              placeholder="e.g. Prioritize QBs early, cheap RBs, elite WRs...")

background_info = build_background_info(rosters, draft_strategy)

# Budgets
st.subheader("💰 Remaining Budgets")
st.write(remaining_budget)

# ----------------- ROSTER MANAGEMENT -----------------
st.subheader("🛠 Manage Rosters")
with st.form("roster_manager"):
    team_choice = st.selectbox("Select Team", list(rosters.keys()))
    slot_choice = st.selectbox("Select Roster Slot", list(rosters[team_choice].keys()))
    player_name = st.text_input("Player Name", placeholder="e.g. Justin Jefferson")
    player_cost = st.number_input("Cost ($)", min_value=0, max_value=TOTAL_BUDGET, step=1)
    action = st.radio("Action", ["Add/Update Player", "Remove Player"])
    submitted = st.form_submit_button("💾 Save Changes")

    if submitted:
        if action == "Add/Update Player":
            rosters[team_choice][slot_choice] = {"player": player_name, "cost": player_cost}
            st.success(f"✅ {player_name} added/updated in {team_choice} ({slot_choice}) for ${player_cost}")
        elif action == "Remove Player":
            rosters[team_choice][slot_choice] = {"player": "", "cost": 0}
            st.warning(f"🗑 Removed player from {team_choice} ({slot_choice})")

        with open("rosters.yml", "w", encoding="utf-8") as file:
            yaml.safe_dump(rosters, file, sort_keys=False, allow_unicode=True)
        st.rerun()

# ----------------- NOMINATION -----------------
st.subheader("📢 Who Should I Nominate?")
if st.button(f"Suggest Nomination for {user_team}"):
    pick = who_should_i_nominate(background_info, user_team, remaining_budget[user_team])
    st.text(pick)

# ----------------- BID -----------------
st.subheader("🤔 Should I Bid?")
other_team = st.selectbox("Which team nominated the player?", [t for t in rosters.keys() if t != user_team])
player = st.text_input("Nominated Player", placeholder="e.g. Joe Burrow, QB")

if st.button("Evaluate Bid"):
    if player.strip():
        bid_advice = should_i_bid(background_info, user_team, other_team, player, remaining_budget[user_team])
        st.text(bid_advice)
    else:
        st.warning("Please enter a player before evaluating the bid.")

# ----------------- ROSTER VIEWER -----------------
st.subheader("📋 View Team Roster")
view_team = st.selectbox("Select a team to view", list(rosters.keys()))

if st.button(f"Show {view_team}'s Roster"):
    df = roster_to_df(rosters[view_team])
    st.dataframe(df, use_container_width=True)
    st.caption(f"💰 Remaining Budget: **${remaining_budget[view_team]}**")
