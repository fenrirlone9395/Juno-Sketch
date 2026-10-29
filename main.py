"""JUNO Sketch desktop entry point."""
import logging
from pathlib import Path
import sys

def main():
    logdir=Path.home()/'Library'/'Logs'/'JunoSketch' if sys.platform=='darwin' else Path.home()/'.juno-sketch'
    logdir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=logdir/'app.log',level=logging.INFO)
    from ui.main_window import MainWindow
    app=MainWindow()
    app.mainloop()

if __name__=='__main__':
    main()
