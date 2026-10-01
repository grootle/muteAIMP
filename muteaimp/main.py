import sys

from .ui import ApplicationController


def main():
    controller = ApplicationController()
    sys.exit(controller.run())


if __name__ == "__main__":
    main()
