"""Point d'entrée : python -m agents.planificateur [--simulation] [--maintenant AAAA-MM-JJTHH:MMZ]"""
import sys

from .agent import main

sys.exit(main())
