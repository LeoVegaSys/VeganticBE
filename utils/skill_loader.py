import os


def get_skills_content(skills_file_name : str, skills_folder_name: str = "skills") -> str:
    _FALLBACK_BUSINESS_FACTS = """\
DOMAIN: (business_facts.md not found — running with no domain rules loaded.
Set appropriate QA_BUSINESS_FACTS in .env OR place business_facts.md in skills folder.)
"""

    current_dir = os.path.dirname(os.path.abspath(__file__))
    adjacent_dir = os.path.join(current_dir, '..', skills_folder_name)
    skills_file = os.path.join(adjacent_dir, skills_file_name)

    try:
        with open(skills_file, "r") as f:
            return f.read()
    except Exception as e:
        print(f"[warn] could not load business facts from {skills_file}: {e} — using fallback")
        return _FALLBACK_BUSINESS_FACTS