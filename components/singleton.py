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
                    #logging.error(
                    #    "If this is not true, likely the program is running in the background. Try sudo pkill -f python3 in the terminal or restart the computer.")
                    #input("Press ENTER to exit...")
                    #sys.exit(-1)
                print(e.errno)
                raise
        else:  # non Windows
            import fcntl, sys
            self.fp = open(self.lockfile, 'w')
            try:
                logging.debug(">>> Opening lock file:", self.lockfile)
                print(">>> Attempting to acquire lock...")

                fcntl.lockf(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
                print(">>> Lock acquired successfully.")
            except IOError:
                import traceback
                print(">>> LOCK ACQUIRE FAILED!")
                print("Exception:", e)
                traceback.print_exc()
                logging.warning("Another instance is already running, quitting.")
                sys.exit(-1)
                #logging.warning("Another instance is already running, quitting.")
                #logging.error(
                #    "If this is not true, likely the program is running in the background. Try sudo pkill -f python3 in the terminal or restart the computer.")
                #input("Press ENTER to exit...")
                #sys.exit(-1)

    def __del__(self):
        try:
            # Directly use already-imported modules
            # e.g. if you did `import os` at top of file
            os.unlink(self.lockfile)
        except Exception:
            # swallow *all* errors—especially at shutdown
            pass
