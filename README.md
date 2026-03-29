# RIPApplemusic

I no want Apple Music.  
I buy old iPod to listen to music.

RIPApplemusic is a simple Mac tool that takes a `.txt` playlist export from iTunes or Apple Music and downloads the songs locally as `.mp3` files.

It has a friendly GUI, and it also works in the terminal.

## What it does

- Reads exported `.txt` playlists from Apple Music / iTunes
- Finds each song automatically
- Downloads audio as MP3
- Adds metadata and thumbnail
- Skips songs you already downloaded
- Saves failed downloads to a log

## Mac only

This project is made for macOS.

## Requirements

You need:

- `yt-dlp`
- `ffmpeg`

Install with Homebrew:

```bash
brew install yt-dlp ffmpeg
