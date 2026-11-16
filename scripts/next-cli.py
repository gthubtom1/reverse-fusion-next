"""Absolute cross-project CLI entry; target-local module names cannot shadow the tool."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rea_enhanced.cli import main

if __name__=='__main__':raise SystemExit(main())
