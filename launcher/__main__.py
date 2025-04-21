#!/usr/bin/env python
"""
Main entry point for the bitHuman Visual Agent Launcher.
Usage: python -m launcher [args]
"""

import sys

from launcher.main import launch_app, parser

if __name__ == "__main__":
    # Parse command line arguments
    args = parser.parse_args()

    # Launch the app with the given arguments
    exit_code = launch_app(port=args.port, verbose=args.verbose)

    # Exit with the returned code
    sys.exit(exit_code)
