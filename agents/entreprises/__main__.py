"""Point d'entrée : python -m agents.entreprises --mode complet|quotidien|assembler [--lot …] [--echantillon N] [--test]"""
import sys

from .agent import main

sys.exit(main())
