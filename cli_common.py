#!/usr/bin/env python3
"""
Shared console-navigation primitives for the HR Screening Tool v2.

These helpers (headers, numbered menus, back-navigation) are used by both the
main screening tool and the bundled BambooHR resume downloader so that every
feature is navigated the exact same way.  Keeping them in one module means the
``BackToMenu`` exception is a single shared class — a ``BackToMenu`` raised deep
inside the downloader is caught by the same ``except BackToMenu`` blocks the
main tool already uses.
"""

import sys


class BackToMenu(Exception):
    """Raised when the user types 'b'/'back' (or '0' in a submenu) to go back."""
    pass


def print_header(title):
    width = 62
    print("\n" + "-" * width)
    print(f"  {title}")
    print("-" * width)


def print_menu(options):
    """Print a numbered menu and return the user's choice. '0' exits the program."""
    for i, option in enumerate(options, 1):
        print(f"  [{i}] {option}")
    print("  [0] Exit")
    print()
    while True:
        choice = input("  Select an option: ").strip()
        if choice == "0":
            print("\n  Goodbye!\n")
            sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice)
        print("  [!]  Invalid choice. Please try again.")


def print_submenu(options):
    """Print a numbered submenu with [0] Back. Raises BackToMenu on '0'."""
    for i, option in enumerate(options, 1):
        print(f"  [{i}] {option}")
    print("  [0] Back to Main Menu")
    print()
    while True:
        choice = input("  Select an option: ").strip()
        if choice == "0":
            print("\n  <<  Returning to Main Menu...\n")
            raise BackToMenu()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice)
        print("  [!]  Invalid choice. Please try again.")


def nav_input(prompt):
    """
    Wrapper around input() that raises BackToMenu when the user types 'b' or 'back'.
    """
    value = input(f"{prompt}  (or 'b' to go back)\n  > ").strip()
    if value.lower() in ("b", "back"):
        print("\n  <<  Returning to Main Menu...\n")
        raise BackToMenu()
    return value
