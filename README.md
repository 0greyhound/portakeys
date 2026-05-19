# PortaKeys

A customizable virtual on-screen keyboard for Windows with keystroke translation support.

## Features

- **Virtual Keyboard**: Clickable on-screen keyboard with multiple layouts
- **Keystroke Translation**: Define custom stroke patterns that auto-translate to target characters
- **Physical Keyboard Hook**: Captures physical keystrokes and applies translations
- **Customizable Layouts**: Create and edit keyboard layouts via GUI or JSON
- **Always on Top**: Keep the keyboard visible while typing
- **Click-Through Mode**: Non-interactive overlay mode

## Usage

1. Run `python portakeys.py`
2. Select a layout from the dropdown (Full ANSI, Numpad, etc.)
3. Click keys to type, or use physical keyboard with translation support

## Keystroke Translation

Define patterns in the Translations dialog (Translations button):
- Example: `]]]` → `a` (type three right-brackets, get 'a')
- Useful for keyboards with broken/missing keys

**Note**: Due to the high-speed nature of input processing, rapidly repeated keystrokes may occasionally cause the script to miss clearing the leading characters. For best results, type at a moderate pace when using translation patterns.

## Custom Layouts

Create custom layouts via:
1. **GUI**: Click "New" → Edit Mode → Arrange keys → Save
2. **JSON**: Edit files in `layouts/` directory

## Platform Support

**Currently Windows-only** - The app relies on Windows-specific APIs (`SendInput`, `SetWindowsHookEx`) for sending keystrokes and capturing physical keyboard input.

On Linux/macOS, the GUI will display but keystrokes won't be sent to other applications.

**Want cross-platform support?** ⭐ Star this repository! If we get enough interest, we'll add Linux (X11/Wayland) and macOS (Quartz) support.

## Requirements

- Windows
- Python 3.x
- No external dependencies (uses built-in tkinter)

## Files

- `portakeys.py` - Main application
- `layouts/` - Keyboard layout JSON files
- `portakeys.config.json` - User settings (created on first run)

## License

MIT
