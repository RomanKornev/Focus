import datetime
import gzip
import math
import os
import time
from collections import OrderedDict, namedtuple
from datetime import datetime as dt

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm_notebook

import ujson

LOGS = './logs/'
Window = namedtuple('Window', 'pid name start_time last_update focus_time exe cmd')
Event = namedtuple('Event', 'time category text index')

SEC_PER_HOUR = 60*60
MS_HOUR_FORMAT = SEC_PER_HOUR/10**3
DAY = pd.Timedelta('1 day')
HOUR = pd.Timedelta('1 hour')
MINUTE = pd.Timedelta('1 minute')

MIN_TIME_PER_CATEGORY = 20*MINUTE  # Display categories with at least 20 minutes total focus time


def load_filter(filename):

    def expand_multi_dict(key_val_pair):
        ret = []
        for item in key_val_pair:
            if type(item[0]) != list:
                ret.append(item)
            else:
                for sub_item in item[0]:
                    ret.append((sub_item, item[1]))
        return ret

    with open(filename, 'r', encoding='utf-8') as f:
        data = OrderedDict(expand_multi_dict(ujson.load(f)))
    return data


def load_data(last_n_days=30):

    def load_gz(file):
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

    files = {file: os.path.getctime(os.path.join(LOGS, file)) for file in os.listdir(LOGS)}
    split_date = (dt.fromtimestamp(files[sorted(files.keys())[-1]]) -
                  pd.Timedelta(str(last_n_days) + 'days')).date()
    data = None
    days = []
    for file in tqdm_notebook(files):
        if dt.fromtimestamp(files[file]).date() > split_date:
            day = load_gz(os.path.join(LOGS, file))
            day = pd.DataFrame.from_records(day, columns=Window._fields)
            day['boot'] = pd.Timestamp(day['start_time'].min())
            days.append(day)

    data = pd.concat([*days])
    data['start_time'] = data['start_time'].apply(lambda x: pd.Timestamp(x))
    data['last_update'] = data['last_update'].apply(lambda x: pd.Timestamp(x))
    data['focus_time'] = data['focus_time'].apply(lambda x: pd.Timedelta(x))
    data['start_time'] = data['last_update'] - data['focus_time']

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

    if data is not None:
        data['category'] = merge(
            data['name'].apply(lambda x: categorize(x, categories_name)).values,
            data['exe'].apply(lambda x: categorize(x, categories_exe)).values,
            data['exe'].str.split('\\').apply(lambda x: x[-1]).values)

    # Delete unused columns
    del data['pid']
    del data['exe']
    return data


def time_ticks(x, pos):
    return str(datetime.timedelta(milliseconds=x*MS_HOUR_FORMAT))


def label_ticks(y, pos):
    return sequence_categories[int(round(y))]


def date_boot_ticks(x, pos):
    return (boot_time_round +
            datetime.timedelta(milliseconds=x*MS_HOUR_FORMAT)).strftime("%Y-%m-%d %H:%M:%S")


def total_days(data):
    return (data.start_time.max() - data.start_time.min())/DAY


def timedelta_to_ms_hr(td):
    return td/np.timedelta64(1, 'ms')/MS_HOUR_FORMAT


def bound_data(data, start_date, end_date):
    start_date = clip_start_date(start_date, data)
    end_date = clip_end_date(end_date, data)
    data_bounded = data[(data.start_time > pd.Timestamp(start_date)) &
                        (data.start_time <= pd.Timestamp(end_date))]
    assert not data_bounded.empty
    return data_bounded, start_date, end_date


def filter_data(data, ignored_categories):
    return data[~data.category.isin(map(str.lower, ignored_categories))]


def reindex_by_total_time_cut(data, category_count):
    data['sum'] = data.sum(axis=1)
    data = data.sort_values('sum', ascending=False)
    data = cut_categories(data, category_count, total_column='sum')
    data = data[::-1]
    del data['sum']
    return data


def cut_categories(data, category_count, total_column=slice(None)):
    if category_count:
        data = data[:category_count]
    else:
        data = data[data[total_column] > MIN_TIME_PER_CATEGORY]
    return data


def redact(plot_data, anonymize, reverse=False):
    linspace = range(len(plot_data))
    if reverse:
        linspace = linspace[::-1]
    if anonymize:
        plot_data.index = [f'REDACTED_{i:02}' for i in linspace]
    return plot_data


def total_time_by_category_boot(data):
    d = data.groupby(['category', 'boot'])['focus_time'].sum()
    d = d.sort_values(ascending=False).unstack(level=1)
    return d


def total_time_by_category_day(data):  # SLOW
    d = data.set_index('start_time').groupby('category')['focus_time'].resample('D').sum().apply(
        timedelta_to_ms_hr)
    d = d.sort_values(ascending=False).unstack(level=1)
    return d


def top_categories_index(data, category_count):
    d = data.groupby('category')['focus_time'].sum()  # Total time per category
    d = d.sort_values(ascending=False)[:category_count].index
    return d


def clip_start_date(date, data):
    if date:
        # Clip to minimum date in all dataset
        date = max(data.start_time.min(), pd.Timestamp(date))
    else:
        # Default to recent month
        date = pd.Timestamp.now() - pd.Timedelta('31 days')
    return date


def clip_end_date(date, data):
    if date:
        # Clip to maximum date in all dataset
        date = min(data.start_time.max(), pd.Timestamp(date))
    else:
        # Default to today
        date = pd.Timestamp('today')
    return date


# Categorizes data points by window_name (first match)
# Format: ([list of window_names] , category) or (window_name , category)
categories_name = load_filter('categories_name_filter.json')

# Categorizes data points by exe_path
# Format: ([list of exe_paths] , category) or (exe_path , category)
categories_exe = load_filter('categories_exe_filter.json')
