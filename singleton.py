import logging
import os
import tempfile

# Literally shamelessly stolen from https://pythonhosted.org/tendo/_modules/tendo/singleton.html#SingleInstance

class SingleInstance:

    def __init__(self):
        import sys
        self.lockfile = os.path.normpath(tempfile.gettempdir() + '/' +
                                         os.path.splitext(os.path.abspath(__file__))[0].replace("/", "-").replace(":",
                                                                                                                  "").replace(
                                             "\\", "-") + '.lock')
        logging.debug("SingleInstance lockfile: " + self.lockfile)
        if sys.platform == 'win32':
            try:
                # file already exists, we try to remove (in case previous execution was interrupted)
                if os.path.exists(self.lockfile):
                    os.unlink(self.lockfile)
                self.fd = os.open(self.lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except OSError as e:
                if e.errno == 13:
                    logging.error("Another instance is already running, quitting.")
                    sys.exit(-1)
                print(e.errno)
                raise
        else:  # non Windows
            import fcntl, sys
            self.fp = open(self.lockfile, 'w')
            try:
                fcntl.lockf(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                logging.warning("Another instance is already running, quitting.")
                sys.exit(-1)

    def __del__(self):
        import sys
        if sys.platform == 'win32':
            if hasattr(self, 'fd'):
                os.close(self.fd)
                os.unlink(self.lockfile)