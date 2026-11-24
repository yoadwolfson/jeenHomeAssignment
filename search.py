"""Search the indexed documents: python search.py --query "<text>" """

import sys

from docindex.bootstrap import ServiceFactory
from docindex.cli import run_cli
from docindex.commands import SearchCommand

if __name__ == "__main__":
    sys.exit(run_cli(SearchCommand(ServiceFactory())))
