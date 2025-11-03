#!/usr/bin/env python3
"""
Test script to verify Claude stream-json output format
"""

import subprocess
import json
import sys

def test_stream_json():
    """Test Claude's stream-json output."""
    print("Testing Claude stream-json output...\n")

    command = [
        "claude",
        "-p", "Say hello and explain what 2+2 equals",
        "--output-format", "stream-json",
        "--allowedTools", "Bash"
    ]

    print(f"Command: {' '.join(command)}\n")
    print("=" * 60)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    line_count = 0
    for line in process.stdout:
        if not line.strip():
            continue

        line_count += 1
        print(f"\n--- Line {line_count} ---")
        print(f"Raw: {line[:100]}...")

        try:
            data = json.loads(line)
            print(f"Type: {data.get('type', 'unknown')}")

            if 'text' in data:
                print(f"Text: {data['text'][:100]}")
            elif 'content' in data:
                print(f"Content: {str(data['content'])[:100]}")

            # Print full JSON structure for first few lines
            if line_count <= 3:
                print(f"Full JSON: {json.dumps(data, indent=2)[:500]}")

        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")

    process.wait()
    print("\n" + "=" * 60)
    print(f"Process exited with code: {process.returncode}")
    print(f"Total lines: {line_count}")

if __name__ == "__main__":
    test_stream_json()
