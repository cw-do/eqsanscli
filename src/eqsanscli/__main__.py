"""Entry point for eqsanscli: python -m eqsanscli"""

from eqsanscli.app import EQSANSApp


def main() -> None:
    """Launch the EQSANS CLI application."""
    app = EQSANSApp()
    app.run()


if __name__ == "__main__":
    main()
