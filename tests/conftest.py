import sys

# Add the handlers directory to the path so pytest can find trade_handler
# import os
# os.path.join(os.path.dirname(__file__), "..")

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT))