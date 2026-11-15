"""Entry point of the packaged app: the program ``MiSalud.exe`` runs.

PyInstaller needs a script, not a function, to start from. This one only hands
over to the app.
"""

from misalud.interface.window import main

if __name__ == "__main__":
    main()
