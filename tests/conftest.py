import os
import sys


# Garante que o diretório do projeto (backend) esteja no sys.path
# para que `import app...` funcione nos testes.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

