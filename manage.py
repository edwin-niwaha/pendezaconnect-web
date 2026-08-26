#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys

from dotenv import load_dotenv

from core.settings import get_settings_module

load_dotenv()


def main():
    """Run administrative tasks."""

    command = sys.argv[1] if len(sys.argv) > 1 else None
    # Always derive the settings module from DJANGO_ENV for management
    # commands. A stale shell-level DJANGO_SETTINGS_MODULE must not make the
    # local runserver use production settings (including HTTPS redirects).
    os.environ["DJANGO_SETTINGS_MODULE"] = get_settings_module(
        os.environ.get("DJANGO_ENV"), command
    )
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
