"""Point d'entrée : python -m agents.macro [--test] [--capturer]"""
import sys

from .agent import main

sys.exit(main())
