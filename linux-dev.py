import os
from subprocess import Popen, PIPE
import time
import psutil as ps

time.sleep(1)

#xdotool getwindowpid $(xdotool getactivewindow)
#xdotool getwindowname $(xdotool getactivewindow)
active_window = Popen(['xdotool', 'getactivewindow'], stdout=PIPE).communicate()[0]
active_pid = int(Popen(['xdotool', 'getwindowpid', active_window], stdout=PIPE).communicate()[0])
active_name = Popen(['xdotool', 'getwindowname', active_window], stdout=PIPE).communicate()[0]
active_name = str(active_name[:-1].decode('utf-8'))

print(active_window, active_name, active_pid)

print(ps.Process(active_pid).exe())

print(Popen(['xprintidle'], stdout=PIPE).communicate()[0])
