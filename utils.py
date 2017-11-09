import pandas as pd
from collections import namedtuple, OrderedDict
import datetime
import ujson
import os
import numpy as np
from datetime import datetime as dt
import matplotlib.pyplot as plt
import math
import time
import gzip

LOGS = './logs/'
Window = namedtuple('Window', 'pid name start_time last_update focus_time exe cmd')
Event = namedtuple('Event', 'time category text index')

CUTOFF = 20*1e6/60  # display categories with at least 20 minutes total focus time

def load(file):
    try:
        if file.split('.')[-1] == 'gz':
            with gzip.open(file) as f:
                data = ujson.loads(f.read().decode('utf-8'))
        else:
            with open(file, encoding='utf-8') as f:
                data = ujson.load(f)
    except:
        print(f'Error loading file: {file}')
    return [Window(*v) for v in data]

def load_data(last_n_days=30):
    global categories_name, categories_exe
    # categorizes data points by window_name (first match)
    # format: ([list of window_names] , category) or (window_name , category)
    with open('categories_name_filter.json', 'r', encoding='utf-8') as f:
        categories_name = OrderedDict(expand_multi_dict(ujson.load(f)))

    # categorizes data points by exe_path
    # format: ([list of exe_paths] , category) or (exe_path , category)
    with open('categories_exe_filter.json', 'r', encoding='utf-8') as f:
        categories_exe = OrderedDict(expand_multi_dict(ujson.load(f)))


    files = {file : os.path.getctime(os.path.join(LOGS, file)) for file in os.listdir(LOGS)}
    split_date = (dt.fromtimestamp(files[sorted(files.keys())[-1]])
                  - pd.Timedelta(str(last_n_days) + 'days')).date()
    data = None
    days = []

    for file in log_progress(files, every=1):
        if dt.fromtimestamp(files[file]).date() > split_date:
            day = load(os.path.join(LOGS, file))
            day = pd.DataFrame.from_records(day, columns=Window._fields)
            day['boot'] = pd.Timestamp(day['start_time'].min())
            days.append(day)

    data = pd.concat([*days])
    data['start_time'] = data['start_time'].apply(lambda x : pd.Timestamp(x))
    data['last_update'] = data['last_update'].apply(lambda x : pd.Timestamp(x))
    data['focus_time'] = data['focus_time'].apply(lambda x : pd.Timedelta(x))
    data['start_time'] = data['last_update'] - data['focus_time']

    if data is not None:
        data['category'] = merge(data['name'].apply(lambda x: categorize(x, categories_name)).values,
                                 data['exe'].apply(lambda x: categorize(x, categories_exe)).values,
                                 data['exe'].str.split('\\').apply(lambda x: x[-1]).values)

    #delete unused columns
    del data['pid']
    del data['exe']
    del data['cmd']
    return data

def reindex(colname):
    data.index = data[colname]
    data.sort_index(inplace=True, ascending=False)
    return data

def expand_multi_dict(key_val_pair):
    ret = []
    for item in key_val_pair:
        if type(item[0]) != list:
            ret.append(item)
        else:
            for sub_item in item[0]:
                ret.append((sub_item, item[1]))
    return ret

def categorize(x, dictionary):
    for k, v in dictionary.items():
        if k.lower() in x.lower():
            return v

def merge(*lists):
    ret = lists[0]
    for l in lists[:-1]:
        assert len(l) == len(lists[-1])
    for i in range(len(lists[0])):
        for l in lists:
            if l[i]:
                ret[i] = l[i]
                break
    return ret

def time_ticks(x, pos):
    return str(datetime.timedelta(milliseconds=x*3.6))

def label_ticks(y, pos):
    return sequence_categories[int(round(y))]

def date_boot_ticks(x, pos):
    return (boot_time_round + datetime.timedelta(milliseconds=x*3.6)).strftime("%Y-%m-%d %H:%M:%S")

def timedelta_to_ms_hr(td):
    return td / np.timedelta64(1,'ms') / 3.6

def reindex_by_sum(data):
    data['sum'] = data.sum(1)
    data = data[data['sum'] > CUTOFF].sort_values('sum')
    del data['sum']
    return data

def total_time_by_category_boot(data):
    d = data.groupby(['category', 'boot'])['focus_time'].sum().apply(timedelta_to_ms_hr)
    d = d.sort_values(ascending=False).unstack(level=1)
    return d

def total_time_by_category_day(data):  # SLOW
    d = data.set_index('start_time').groupby('category')['focus_time'].resample('D').sum().apply(timedelta_to_ms_hr)
    d = d.sort_values(ascending=False).unstack(level=1)
    return d

def top_categories_index(data, category_count):
    total_category_time = data.groupby('category')['focus_time'].sum()
    return total_category_time.sort_values(ascending=False)[:category_count].index

def clip_start_date(date):
    if date:
        # clip to minimum date in all dataset
        date = max(data.start_time.min(), pd.Timestamp(date))
    else:
        # default to recent month
        date = pd.Timestamp.now() - pd.Timedelta('31 days')
    return date

def clip_end_date(date):
    if date:
        # clip to maximum date in all dataset
        date = min(data.start_time.max(), pd.Timestamp(date))
    else:
        # default to today
        date = pd.Timestamp('today')
    return date

def log_progress(sequence, every=None, size=None):
    from ipywidgets import IntProgress, HTML, VBox
    from IPython.display import display

    is_iterator = False
    if size is None:
        try:
            size = len(sequence)
        except TypeError:
            is_iterator = True
    if size is not None:
        if every is None:
            if size <= 200:
                every = 1
            else:
                every = size / 200     # every 0.5%
    else:
        assert every is not None, 'sequence is iterator, set every'

    if is_iterator:
        progress = IntProgress(min=0, max=1, value=1)
        progress.bar_style = 'info'
    else:
        progress = IntProgress(min=0, max=size, value=0)
    label = HTML()
    box = VBox(children=[label, progress])
    display(box)

    index = 0
    try:
        for index, record in enumerate(sequence, 1):
            if index == 1 or index % every == 0:
                if is_iterator:
                    label.value = '{index} / ?'.format(index=index)
                else:
                    progress.value = index
                    label.value = u'{index} / {size}'.format(
                        index=index,
                        size=size
                    )
            yield record
    except:
        progress.bar_style = 'danger'
        raise
    else:
        progress.bar_style = 'success'
        progress.value = index
        label.value = str(index or '?')

data = load_data(365)
