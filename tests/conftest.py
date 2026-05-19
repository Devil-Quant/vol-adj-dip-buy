"""Make `import strategies.dip_buy` work when pytest is run from project root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
