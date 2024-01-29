import atexit
from time import time, strftime, localtime
from datetime import timedelta

def secondsToStr(elapsed=None):
    if elapsed is None:
        return strftime("%Y-%m-%d %H:%M:%S", localtime())
    else:
        return str(timedelta(seconds=elapsed))

def endlog():
    end = time()
    elapsed = end-start
    print(f"Elapsed time: {elapsed:.2f} sec")

start = time()
atexit.register(endlog)
# https://stackoverflow.com/a/12344609/4443082