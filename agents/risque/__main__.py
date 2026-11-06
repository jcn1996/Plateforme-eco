"""Point d'entrée : python -m agents.risque [--test] [--mode horaire|complet]"""
import sys

from .agent import main

sys.exit(main())
