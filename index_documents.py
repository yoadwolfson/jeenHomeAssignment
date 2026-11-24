"""Index a PDF or DOCX file: python index_documents.py --file <path> --strategy {fixed,sentence,paragraph}"""

import sys

from docindex.bootstrap import ServiceFactory
from docindex.cli import run_cli
from docindex.commands import IndexCommand

if __name__ == "__main__":
    sys.exit(run_cli(IndexCommand(ServiceFactory())))
