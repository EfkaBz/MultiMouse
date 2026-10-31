import os
import sys

if __package__ in (None, ""):  # frozen executable or `python multimouse/__main__.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from multimouse.app import main
else:
    from .app import main

if __name__ == "__main__":
    main()
