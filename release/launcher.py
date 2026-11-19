"""Entry point of the packaged app: the program ``HealthLab.exe`` runs.

PyInstaller needs a script, not a function, to start from. This one only hands
over to the app.
"""

from healthlab.interface.window import main

if __name__ == "__main__":
    main()
