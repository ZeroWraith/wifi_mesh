"""Allow ``python -m meshd`` to run the daemon."""

import sys

from meshd.main import main

if __name__ == "__main__":
    sys.exit(main())
