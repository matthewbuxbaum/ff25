import streamlit as st
import re
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI()


# --- Load & parse cheat sheet ---
@st.cache_data
def load_cheat_sheet():
    cheat_sheet = {"QB": [], "RB": [], "WR": [], "TE": []}
    current_position = None

    with open("cheat_sheet.md", "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Detect section
            if line.startswith("Top QB"):
                current_position = "QB"
                continue
            elif line.startswith("Top RB"):
                current_position = "RB"
                continue
            elif line.startswith("Top WR"):
                current_position = "WR"
                continue
            elif line.startswith("TOP TE"):
                current_position = "TE"
                continue

            # Parse players
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


# --- Helpers ---
def get_available_players(position, drafted, top_n=20):
    """Return top N undrafted players for a position."""
    sheet = load_cheat_sheet()
    return [
               p for p in sheet[position]
               if p["name"] not in drafted
           ][:top_n]


def rosters_summary(rosters):
    """Create a compressed summary of all rosters."""
    summary = []
    for user, players in rosters.items():
        summary.append(f"{user}: {', '.join(players) if players else 'No players yet'}")
    return "\n".join(summary)


# --- Streamlit UI ---
st.title("🏈 2QB Auction Draft Assistant")

if "rosters" not in st.session_state:
    st.session_state.rosters = {
        "You": [],
        "Opponent1": [],
        "Opponent2": []
    }
if "drafted" not in st.session_state:
    st.session_state.drafted = set()

# Input controls
position = st.selectbox("Choose a position:", ["QB", "RB", "WR", "TE"])
user_action = st.radio("Action:", ["Nominate", "Bid Advice"])

if st.button("Ask Assistant"):
    # Get available players for that position
    available = get_available_players(position, st.session_state.drafted)

    # Build context
    context = f"""
    Current rosters:
    {rosters_summary(st.session_state.rosters)}

    Available top {len(available)} {position}s:
    {', '.join([p['name'] + ' ($' + str(p['cost']) + ')' for p in available])}
    """

    # Stream OpenAI response
    st.subheader("Assistant's Advice:")
    response_area = st.empty()
    full_response = ""

    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert fantasy football draft assistant."},
            {"role": "user", "content": f"Action: {user_action}\n\n{context}"}
        ],
        stream=True,
    )

    for chunk in stream:
        if token := chunk.choices[0].delta.get("content"):
            full_response += token
            response_area.text(full_response)

# --- Update rosters ---
st.sidebar.header("Drafted Players")
for team, players in st.session_state.rosters.items():
    st.sidebar.write(f"**{team}**: {', '.join(players) if players else 'None'}")

with st.sidebar.expander("Update Draft Board"):
    team = st.selectbox("Team", list(st.session_state.rosters.keys()))
    player = st.text_input("Player drafted")

    if st.button("Add Player"):
        if player:
            st.session_state.rosters[team].append(player)
            st.session_state.drafted.add(player)
            st.success(f"Added {player} to {team}'s roster")
