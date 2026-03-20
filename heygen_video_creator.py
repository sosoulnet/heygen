#!/usr/bin/env python3
"""
HeyGen Video Creator
Reads text files from a folder and creates HeyGen videos from each one.

Usage:
    python heygen_video_creator.py /path/to/text/files

Requirements:
    - HEYGEN_API_KEY environment variable (or set in .env file)
    - HEYGEN_AVATAR_ID environment variable (get from HeyGen API or dashboard)
    - HEYGEN_VOICE_ID environment variable (get from HeyGen API or dashboard)

Note: HeyGen's API requires an avatar for video generation. To find available
avatars and voices, run:
    python heygen_video_creator.py --list-avatars
    python heygen_video_creator.py --list-voices
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.heygen.com"
MAX_TEXT_LENGTH = 5000
POLL_INTERVAL = 10  # seconds between status checks
MAX_POLL_TIME = 600  # max seconds to wait for a video


def get_headers():
    api_key = os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        print("Error: HEYGEN_API_KEY environment variable is not set.")
        print("Get your API key from https://app.heygen.com/settings?nav=API")
        sys.exit(1)
    return {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def list_avatars():
    """List available avatars from HeyGen."""
    resp = requests.get(f"{API_BASE}/v2/avatars", headers=get_headers())
    resp.raise_for_status()
    data = resp.json()
    avatars = data.get("data", {}).get("avatars", [])
    print(f"\nFound {len(avatars)} avatars:\n")
    for av in avatars:
        print(f"  ID: {av.get('avatar_id')}")
        print(f"  Name: {av.get('avatar_name', 'N/A')}")
        print()
    return avatars


def list_voices():
    """List available voices from HeyGen."""
    resp = requests.get(f"{API_BASE}/v2/voices", headers=get_headers())
    resp.raise_for_status()
    data = resp.json()
    voices = data.get("data", {}).get("voices", [])
    print(f"\nFound {len(voices)} voices:\n")
    for v in voices:
        print(f"  ID: {v.get('voice_id')}")
        print(f"  Name: {v.get('name', 'N/A')}")
        print(f"  Language: {v.get('language', 'N/A')}")
        print(f"  Gender: {v.get('gender', 'N/A')}")
        print()
    return voices


def create_video(text, title, avatar_id, voice_id):
    """Submit a video generation request to HeyGen.

    Uses portrait orientation (720x1280) and generate mode (not chat/streaming).
    """
    if len(text) > MAX_TEXT_LENGTH:
        print(f"  Warning: Text is {len(text)} chars, truncating to {MAX_TEXT_LENGTH}")
        text = text[:MAX_TEXT_LENGTH]

    payload = {
        "title": title,
        "caption": False,
        "dimension": {
            "width": 720,
            "height": 1280,
        },
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": text,
                    "voice_id": voice_id,
                },
                "background": {
                    "type": "color",
                    "value": "#000000",
                },
            }
        ],
    }

    resp = requests.post(
        f"{API_BASE}/v2/video/generate",
        headers=get_headers(),
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"API error: {data['error']}")

    video_id = data.get("data", {}).get("video_id")
    if not video_id:
        raise RuntimeError(f"No video_id in response: {data}")

    return video_id


def wait_for_video(video_id):
    """Poll HeyGen until the video is completed or failed."""
    url = f"{API_BASE}/v1/video_status.get"
    elapsed = 0

    while elapsed < MAX_POLL_TIME:
        resp = requests.get(url, headers=get_headers(), params={"video_id": video_id})
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status")

        if status == "completed":
            return data.get("video_url")
        elif status == "failed":
            error = data.get("error", "Unknown error")
            raise RuntimeError(f"Video generation failed: {error}")
        else:
            print(f"  Status: {status} (waited {elapsed}s)...")
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

    raise TimeoutError(f"Video {video_id} did not complete within {MAX_POLL_TIME}s")


def download_video(video_url, output_path):
    """Download the completed video to a local file."""
    resp = requests.get(video_url, stream=True)
    resp.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def get_text_files(folder):
    """Get all .txt files in the given folder (non-recursive)."""
    folder = Path(folder)
    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory.")
        sys.exit(1)
    files = sorted(folder.glob("*.txt"))
    if not files:
        print(f"No .txt files found in '{folder}'.")
        sys.exit(1)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Create HeyGen videos from text files in a folder."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="Path to folder containing .txt files",
    )
    parser.add_argument(
        "--list-avatars",
        action="store_true",
        help="List available HeyGen avatars and exit",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available HeyGen voices and exit",
    )
    parser.add_argument(
        "--avatar-id",
        default=os.environ.get("HEYGEN_AVATAR_ID"),
        help="Avatar ID (or set HEYGEN_AVATAR_ID env var)",
    )
    parser.add_argument(
        "--voice-id",
        default=os.environ.get("HEYGEN_VOICE_ID"),
        help="Voice ID (or set HEYGEN_VOICE_ID env var)",
    )

    args = parser.parse_args()

    if args.list_avatars:
        list_avatars()
        return

    if args.list_voices:
        list_voices()
        return

    if not args.folder:
        parser.error("Please provide a folder path, or use --list-avatars / --list-voices")

    if not args.avatar_id:
        print("Error: No avatar ID provided.")
        print("Set HEYGEN_AVATAR_ID env var, use --avatar-id, or run --list-avatars to find one.")
        sys.exit(1)

    if not args.voice_id:
        print("Error: No voice ID provided.")
        print("Set HEYGEN_VOICE_ID env var, use --voice-id, or run --list-voices to find one.")
        sys.exit(1)

    folder = Path(args.folder).resolve()
    text_files = get_text_files(folder)
    downloads_dir = folder / "downloads"

    print(f"Found {len(text_files)} text file(s) in '{folder}'")
    print(f"Videos will be saved to '{downloads_dir}'")
    print(f"Avatar: {args.avatar_id}")
    print(f"Voice: {args.voice_id}")
    print(f"Orientation: Portrait (720x1280)")
    print(f"Mode: Generate (studio video)\n")

    results = {"success": 0, "failed": 0}

    for txt_file in text_files:
        print(f"Processing: {txt_file.name}")
        text = txt_file.read_text(encoding="utf-8").strip()

        if not text:
            print(f"  Skipping empty file: {txt_file.name}")
            results["failed"] += 1
            continue

        title = txt_file.stem
        output_path = downloads_dir / f"{title}.mp4"

        try:
            print(f"  Submitting video generation...")
            video_id = create_video(text, title, args.avatar_id, args.voice_id)
            print(f"  Video ID: {video_id}")

            print(f"  Waiting for video to complete...")
            video_url = wait_for_video(video_id)

            print(f"  Downloading video...")
            download_video(video_url, output_path)
            print(f"  Saved: {output_path}")
            results["success"] += 1

        except Exception as e:
            print(f"  Error: {e}")
            results["failed"] += 1

        print()

    print(f"Done! Success: {results['success']}, Failed: {results['failed']}")


if __name__ == "__main__":
    main()
