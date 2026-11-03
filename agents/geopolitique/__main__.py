"""Point d'entrée : python -m agents.geopolitique [--test] [--mode horaire|quotidien]"""
import sys

from .agent import main

sys.exit(main())
