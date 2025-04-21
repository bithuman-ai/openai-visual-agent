"""Main entry point for the daemon package when run as a module.

This file allows the daemon to be run with:
    python -m daemon [args]
"""

import argparse
import sys

from daemon.main import run_daemon

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="bitHuman Visual Agent Daemon")
    parser.add_argument("--port", type=int, help="Specify port for the server")
    parser.add_argument("--model", help="Path to the model file")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    args = parser.parse_args()

    # Run the daemon with parsed arguments
    exit_code = run_daemon(model_path=args.model, port=args.port, verbose=args.verbose)

    # Exit with the appropriate code
    sys.exit(exit_code)
