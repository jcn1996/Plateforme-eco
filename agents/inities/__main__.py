"""Point d'entrée : python -m agents.inities [--mode complet|leger] [--test] [--capturer]"""
import sys

from .agent import main

sys.exit(main())
