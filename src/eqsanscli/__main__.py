"""Entry point for eqsanscli: python -m eqsanscli [headless]"""

import sys


def main() -> None:
    """Launch the EQSANS CLI application."""
    if len(sys.argv) > 1 and sys.argv[1] == "headless":
        from eqsanscli.headless import run_headless
        run_headless()
    else:
        from eqsanscli.app import EQSANSApp
        app = EQSANSApp()
        app.run()


if __name__ == "__main__":
    main()
