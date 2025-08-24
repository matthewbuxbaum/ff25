# app.py
import streamlit as st
import yaml
import pandas as pd
from openai import OpenAI

# ----------------- SETUP -----------------
api_key = st.secrets.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

TOTAL_BUDGET = 260


# ----------------- HELPERS -----------------
def open_configs():
    with open("cheat_sheet.md", "r", encoding="utf-8") as file:
        cheat_sheet = file.read()

    with open("rosters.yml", "r", encoding="utf-8") as file:
        rosters = yaml.safe_load(file)

    return cheat_sheet, rosters


def get_remaining_budgets(data: dict, total_budget: int = 260) -> dict:
    remaining = {}
    for team_name, roster in data.items():
        spent = 0
        for slot, info in roster.items():
            if isinstance(info, dict):
                spent += info.get("cost", 0) or 0
        remaining[team_name] = total_budget - spent
    return remaining


def who_should_i_nominate(background_info: str, user_team: str, remaining_budget: int):
    prompt = f"""
    Review {user_team}'s current roster and other teams to determine who they should nominate.
    Consider the player's remaining budget and open roster spots so they can plan to draft an entire team within the budget.
    Consider the estimated auction value provided in the cheat sheet.
    Consider the user-inputted draft strategy.
    Bench players usually go for $1.
    Always return your answer in with:
    - A short intro (1–2 sentences)
    - Use bullet points with 3-5 sentences and actionable advice
    """
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""{background_info} + {prompt} 
        {user_team} has a remaining budget of {remaining_budget}.
        """,
    )
    return response.output_text


def should_i_bid(background_info: str, user_team: str, other_team: str, player: str, remaining_budget: int):
    prompt = f"""
    Should {user_team} bid on this player nominated by {other_team}?
    Consider the player's remaining budget and open roster spots so they can plan to draft an entire team within the budget.
    Consider the estimated auction value provided in the cheat sheet.
    Consider the user-inputted draft strategy.
    Bench players usually go for $1.
    Always return your answer with:
    - A direct yes/no recommendation up front
    - Use bullet points with 3-5 sentences
    """
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""{background_info} + {prompt}
        Team {other_team} nominated {player}.
        {user_team} has {remaining_budget} left.
        """,
    )
    return response.output_text


def roster_to_df(team_roster: dict):
    rows = []
    for slot, info in team_roster.items():
        if isinstance(info, dict):
            rows.append({"Slot": slot, "Player": info.get("player", ""), "Cost": info.get("cost", 0)})
        else:
            rows.append({"Slot": slot, "Player": str(info), "Cost": 0})
    return pd.DataFrame(rows)


# ----------------- STREAMLIT APP -----------------
st.title("🏈 Bux AI: Fantasy Draft Assistant")

league_scoring, cheat_sheet, rosters = open_configs()
remaining_budget = get_remaining_budgets(rosters)

# Dropdown for selecting *your* team
user_team = st.selectbox("Which team are you?", list(rosters.keys()))

# Draft strategy input
draft_strategy = st.text_area("✍️ Enter Your Draft Strategy",
                              placeholder="e.g. Prioritize QBs early, cheap RBs, elite WRs...")

# Build background info
background_info = f"""
This is a 12-team, $260 auction league budget. 2 starting QB's, 1 extra WR/RB/TE flex.  1 full PPR.
Cheat sheet: {cheat_sheet}
Strategy: {draft_strategy}
Rosters: {rosters}
Note: Once a player is drafted on a team, they cannot be drafted again.
"""

# Show remaining budgets
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

        # Save changes to file
        with open("rosters.yml", "w", encoding="utf-8") as file:
            yaml.safe_dump(rosters, file, sort_keys=False, allow_unicode=True)

        st.rerun()

# ----------------- NOMINATION -----------------
st.subheader("📢 Who Should I Nominate?")
if st.button(f"Suggest Nomination for {user_team}"):
    pick = who_should_i_nominate(background_info, user_team, remaining_budget[user_team])
    st.text(pick)   # 👈 raw text output

# ----------------- BID -----------------
st.subheader("🤔 Should I Bid?")
other_team = st.selectbox("Which team nominated the player?", [t for t in rosters.keys() if t != user_team])
player = st.text_input("Nominated Player", placeholder="e.g. Joe Burrow, QB")

if st.button("Evaluate Bid"):
    if player.strip():
        bid_advice = should_i_bid(background_info, user_team, other_team, player, remaining_budget[user_team])
        st.text(bid_advice)   # 👈 raw text output
    else:
        st.warning("Please enter a player before evaluating the bid.")

# ----------------- ROSTER VIEWER -----------------
st.subheader("📋 View Team Roster")
view_team = st.selectbox("Select a team to view", list(rosters.keys()))

if st.button(f"Show {view_team}'s Roster"):
    df = roster_to_df(rosters[view_team])
    st.dataframe(df, use_container_width=True)
    st.caption(f"💰 Remaining Budget: **${remaining_budget[view_team]}**")
