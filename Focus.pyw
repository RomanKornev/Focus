import win32process
import win32gui
import win32api

from collections import namedtuple
import logging
import itertools
import psutil as ps
import datetime as dt
import time
import sys
import os
import ujson
import gzip

UPDATE_TIME = 0.1  # seconds
AUTOSAVE_EVERY = 100  # 100*UPDATE_TIME
AFK_TIME = 300  # seconds
AFK_EXE = 'C:\\Windows\\explorer.exe'  # which process to use as idle process
AFK_TITLE = 'AFK'
AFK_IGNORE = ['youtube', 'twitch']  # windows containing any of these keywords will not set idle timer

Window = namedtuple('Window', ['pid', 'name', 'start_time', 'last_update', 'focus_time', 'exe', 'cmd'])

def dump(data, file):
    try:
        if not os.path.exists(r'./logs/'):
            os.mkdir('logs')
        # replace datetime with string and save *.json.gz
        write = [v._replace(focus_time=str(v.focus_time)) for v in data.values()]
        with gzip.open(file, mode='wb') as f:
            f.write(ujson.dumps(write).encode('utf-8'))
    except PermissionError:
        pass


def load(file):
    if file.split('.')[-1] == 'gz':
        with gzip.open(file) as f:
            data = ujson.loads(f.read().decode('utf-8'))
    else:
        with open(file, encoding='utf-8') as f:
            data = ujson.load(f)
    return [Window(*v) for v in data]


def exception_hook(exc_type, exc_value, exc_traceback):
    logger.error('\nUncaught exception hooked:',
                 exc_info=(exc_type, exc_value, exc_traceback))


def logging_setup():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler('errlog.log', mode='a', encoding='utf-8')
    fh.setLevel(logging.ERROR)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
    sys.excepthook = exception_hook
    return logger


if __name__ == '__main__':
    logger = logging_setup()
    filename = str(dt.datetime.now().strftime("%Y-%m-%d %H-%M-%S"))
    windows = dict()  # window : Window()
    processes = dict()  # pid : process
    cur_time = dt.datetime.now()
    afk = None  # pid of afk process (when found)
    segment = 0
    prev_focus_title = None
    for i in itertools.count():
        try:
            win = win32gui.GetForegroundWindow()
            focus_title = win32gui.GetWindowText(win)
            if win == 0: continue
            pid = win32process.GetWindowThreadProcessId(win)[1]
            if pid not in processes:
                processes[pid] = ps.Process(pid)
            processes[pid].exe()
        except ps.NoSuchProcess as e:
            logger.exception('\nps.NoSuchProcess, pid=%r, win=%r, title=%r', pid, win, focus_title, exc_info=True)
            time.sleep(1)
            continue
        except Exception as e:
            logger.exception('\nException, pid=%r, win=%r, title=%r', pid, win, focus_title, exc_info=True)
            time.sleep(1)
            continue

        if (win32api.GetTickCount() - win32api.GetLastInputInfo()) / 1000 > AFK_TIME and afk:
            if not any(keyword in focus_title.lower() for keyword in AFK_IGNORE):
                pid = afk
                focus_title = AFK_TITLE
        if focus_title != prev_focus_title:
            segment += 1
        prev_focus_title = focus_title
        p = processes[pid]
        if not afk and AFK_EXE in p.exe():
            afk = pid
        window = (str(pid), str(focus_title), str(p.create_time()), str(segment))
        now = dt.datetime.now()
        if window in windows:
            windows[window] = windows[window]._replace(focus_time=windows[window].focus_time + now - cur_time,
                                                       last_update=str(now))
        else:
            windows[window] = Window(pid,
                                     focus_title,
                                     str(dt.datetime.fromtimestamp(p.create_time())),
                                     str(now),
                                     now - cur_time,
                                     p.exe(),
                                     ' '.join(p.cmdline()))
        cur_time = now
        time.sleep(UPDATE_TIME)
        if i % AUTOSAVE_EVERY == 0:
            dump(windows, './logs/{}.json.gz'.format(filename))
