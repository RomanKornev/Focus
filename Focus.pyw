from collections import namedtuple
import logging
import itertools
import psutil as ps
import datetime as dt
import time
import os
import ujson
import gzip
import sys
from subprocess import Popen, PIPE
if 'win32' in sys.platform:
    import win32process
    import win32gui
    import win32api

UPDATE_TIME = 0.1  # seconds
AUTOSAVE_EVERY = 1000  # 1000*UPDATE_TIME
AFK_TIME = 300  # seconds

if 'linux' in sys.platform:
    AFK_EXE = 'compiz' # which process to use as idle process
else:
    AFK_EXE = 'C:\\Windows\\explorer.exe'

AFK_TITLE = 'AFK'
# windows containing any of these keywords will not set idle timer
AFK_IGNORE = list(map(str.lower,
    ['youtube', 'twitch', 'Media Player Classic', '.mp4', '.mov', '.mpg', 
     '.avi', '.mkv', 'VLC', 'stdin', '127.0.0.1']))

Window = namedtuple('Window', 'pid name start_time last_update focus_time exe cmd')


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


def get_process_data(process):
    return (process.create_time(),
            process.exe(),
            process.cmdline())

if __name__ == '__main__':
    logger = logging_setup()
    filename = str(dt.datetime.now().strftime("%Y-%m-%d %H-%M-%S"))
    windows = dict()  # window : Window()
    processes = dict()  # pid : process
    cur_time = dt.datetime.now()
    afk = None  # pid of afk process (when found)
    segment = 0
    prev_focus_title = None
    win = None
    pid = None
    focus_title = None

    for i in itertools.count():
        try:
            if 'linux' in sys.platform:
                win = Popen(['xdotool', 'getactivewindow'], 
                            stdout=PIPE).communicate()[0]
                if not win: continue
                pid = int(Popen(['xdotool', 'getwindowpid', win], 
                                stdout=PIPE).communicate()[0])
                focus_title = Popen(['xdotool', 'getwindowname', win], 
                                    stdout=PIPE).communicate()[0]
                focus_title = str(focus_title[:-1].decode('utf-8'))
            else:
                win = win32gui.GetForegroundWindow()
                focus_title = win32gui.GetWindowText(win)
                if not win: continue
                pid = win32process.GetWindowThreadProcessId(win)[1]
            if pid not in processes:
                processes[pid] = ps.Process(pid)
            proc_data = get_process_data(processes[pid])

        except ps._exceptions.NoSuchProcess as e:
            logger.exception('\nps.NoSuchProcess, pid=%r, win=%r, title=%r', 
                             pid, win, focus_title, exc_info=True)
            time.sleep(1)
            continue
        except PermissionError:
            #logger.exception('\nPermissionError, pid=%r, win=%r, title=%r', pid, win, focus_title, exc_info=True)
            time.sleep(1)
            continue
        except ps._exceptions.AccessDenied:
            time.sleep(1)
            continue
        except Exception as e:
            logger.exception('\nException, pid=%r, win=%r, title=%r', 
                             pid, win, focus_title, exc_info=True)
            time.sleep(1)
            continue

        if 'linux' in sys.platform:
            last_input_time = int(Popen(['xprintidle'], 
                                        stdout=PIPE).communicate()[0])  # milliseconds
        else:
            last_input_time = win32api.GetTickCount() - win32api.GetLastInputInfo()
        if last_input_time / 1000 > AFK_TIME and afk:
            if not any(keyword in focus_title.lower() for keyword in AFK_IGNORE):
                # AFK mode started
                pid = afk
                focus_title = AFK_TITLE
                proc_data = get_process_data(processes[pid])

        if focus_title != prev_focus_title:
            segment += 1
        prev_focus_title = focus_title
        if not afk and AFK_EXE in proc_data[1]:
            afk = pid
        window = (str(pid), str(focus_title), str(proc_data[0]), str(segment))
        now = dt.datetime.now()
        if window in windows:
            new_focus_time = windows[window].focus_time + now - cur_time
            windows[window] = windows[window]._replace(focus_time=new_focus_time,
                                                       last_update=str(now))
        else:
            windows[window] = Window(pid,
                                     focus_title,
                                     str(dt.datetime.fromtimestamp(proc_data[0])),
                                     str(now),
                                     now - cur_time,
                                     proc_data[1],
                                     ' '.join(proc_data[2]))
        cur_time = now
        time.sleep(UPDATE_TIME)
        if i % AUTOSAVE_EVERY == 0:
            logger.debug('saving...')
            dump(windows, './logs/{}.json.gz'.format(filename))
