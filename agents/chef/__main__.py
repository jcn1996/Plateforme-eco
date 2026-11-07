"""Point d'entrée : python -m agents.chef [--test] [--mode complet|leger]"""
import sys

from .agent import main

sys.exit(main())
