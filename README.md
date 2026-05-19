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

1. Run `python "portakeys (2).py"`
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

## Requirements

- Windows
- Python 3.x
- No external dependencies (uses built-in tkinter)

## Files

- `portakeys (2).py` - Main application
- `layouts/` - Keyboard layout JSON files
- `portakeys.config.json` - User settings (created on first run)

## License

MIT
