
import os
import sys
import argparse
import time
from pathlib import Path

def main():
    """
    Tests basic I/O and error handling for the container.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail", action="store_true", help="Intentionally raise an exception.")
    args = parser.parse_args()

    print("--- Docker I/O Test Script Starting ---")

    if args.fail:
        print("Intentional failure flag set. Raising exception to test stderr.")
        raise ValueError("This is a test exception to verify stderr logging.")

    # --- Happy Path --- 
    print("This is a log message to stdout.")
    print("This is a message to stderr.", file=sys.stderr)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "output.txt"
    print(f"Creating output file at: {output_file}")

    with open(output_file, "w") as f:
        f.write(f"File successfully created at {time.time()}.")

    print("--- Docker I/O Test Script Finished Successfully ---")

if __name__ == "__main__":
    main()
