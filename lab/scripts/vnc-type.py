#!/usr/bin/env python3
"""Type text into a VM via virsh send-key, one key at a time with proper delays."""
import subprocess, sys, time

VM = sys.argv[1]
TEXT = sys.argv[2]

KEYMAP = {
    ' ': ['KEY_SPACE'], '/': ['KEY_SLASH'], '-': ['KEY_MINUS'],
    '.': ['KEY_DOT'], ',': ['KEY_COMMA'], '=': ['KEY_EQUAL'],
    '_': ['KEY_LEFTSHIFT', 'KEY_MINUS'],
    ':': ['KEY_LEFTSHIFT', 'KEY_SEMICOLON'],
    ';': ['KEY_SEMICOLON'],
    '#': ['KEY_LEFTSHIFT', 'KEY_3'],
    '!': ['KEY_LEFTSHIFT', 'KEY_1'],
    '@': ['KEY_LEFTSHIFT', 'KEY_2'],
    '$': ['KEY_LEFTSHIFT', 'KEY_4'],
    '"': ['KEY_LEFTSHIFT', 'KEY_APOSTROPHE'],
    "'": ['KEY_APOSTROPHE'],
    '>': ['KEY_LEFTSHIFT', 'KEY_DOT'],
    '<': ['KEY_LEFTSHIFT', 'KEY_COMMA'],
    '|': ['KEY_LEFTSHIFT', 'KEY_BACKSLASH'],
    '\\': ['KEY_BACKSLASH'],
    '(': ['KEY_LEFTSHIFT', 'KEY_9'],
    ')': ['KEY_LEFTSHIFT', 'KEY_0'],
    '+': ['KEY_LEFTSHIFT', 'KEY_EQUAL'],
    '~': ['KEY_LEFTSHIFT', 'KEY_GRAVE'],
    '*': ['KEY_LEFTSHIFT', 'KEY_8'],
    '&': ['KEY_LEFTSHIFT', 'KEY_7'],
}

for char in TEXT:
    if char in KEYMAP:
        keys = KEYMAP[char]
    elif char.isdigit():
        keys = [f'KEY_{char}']
    elif char.isalpha() and char.islower():
        keys = [f'KEY_{char.upper()}']
    elif char.isalpha() and char.isupper():
        keys = ['KEY_LEFTSHIFT', f'KEY_{char}']
    else:
        print(f"Unknown char: {char}", file=sys.stderr)
        continue
    
    cmd = ['virsh', 'send-key', VM] + keys
    subprocess.run(cmd, capture_output=True)
    time.sleep(0.15)  # 150ms between keystrokes

# Send Enter if --enter flag
if len(sys.argv) > 3 and sys.argv[3] == '--enter':
    time.sleep(0.3)
    subprocess.run(['virsh', 'send-key', VM, 'KEY_ENTER'], capture_output=True)
