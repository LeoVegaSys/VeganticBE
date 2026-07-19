DIP_KEYWORDS = ("dip", "dips", "dipped", "drop", "dropped", "surge", "spike",
                "sudden", "fell", "fall", "plunge", "plunged")

def get_query_type(state: dict) -> str:
    query = state['question'].lower()
    if any(w in query for w in DIP_KEYWORDS):
        return "calculate_dip"
    else:
        return "analyze_traffic"
    return "parse_question"