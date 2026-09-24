import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        from epub_translator.cli import main as cli_main
        sys.exit(cli_main())
    else:
        from epub_translator.web_server import main as web_main
        web_main()
