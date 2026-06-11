"""
Shared pytest fixtures and project root setup.
"""
import sys
from pathlib import Path

# Add project root to sys.path so `import spyswat` works without install
sys.path.insert(0, str(Path(__file__).parent.parent))
