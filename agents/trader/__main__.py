"""Point d'entrée : python -m agents.trader [--test] [--mode decision|horaire]"""
import sys

from .agent import main

sys.exit(main())
