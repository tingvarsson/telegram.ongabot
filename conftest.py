import sys
from pathlib import Path

# Add ongabot directory to sys.path to enable imports like "from event import Event"
# This matches the project's import style
ongabot_path = Path(__file__).parent / "ongabot"
if str(ongabot_path) not in sys.path:
    sys.path.insert(0, str(ongabot_path))
