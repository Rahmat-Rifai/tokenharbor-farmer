import os


def find_9router_db() -> str:
    """Find the SQLite database path used by 9Router.

    Checks:
    1. Environment variable NINE_ROUTER_DB (if existing)
    2. ~/AppData/Roaming/9router/db/data.sqlite (Windows standard)
    3. ~/.9router/db/data.sqlite (Unix/User standard)
    4. data.sqlite in local working directory
    Falls back to ~/AppData/Roaming/9router/db/data.sqlite.
    """
    env_db = os.environ.get("NINE_ROUTER_DB", "")
    if env_db and os.path.exists(env_db):
        return env_db

    candidates = [
        os.path.expanduser("~/AppData/Roaming/9router/db/data.sqlite"),
        os.path.expanduser("~/.9router/db/data.sqlite"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.sqlite"),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand

    return os.path.expanduser("~/AppData/Roaming/9router/db/data.sqlite")
