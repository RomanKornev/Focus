# Focus
A tool I wrote for myself to help me keep track of how much time I spend using different programs or browsing web.

Consists of 2 parts: 
- Polling script for data gathering
- Jupyter Notebook for analysis

### Polling script
The polling script continuosly records current window in focus and saves it to ```./logs/``` as ```.json.gz```

It saves data such as pid, window name, process creation time, time in focus, executable path, command line arguments.
Every switch of a window is a new data point (to make a sequence plot described below).

It also filters any idle time into a different data group and has keywords that won't set the idle timer.

If it lacks permissions or another error occurs, it will put window names with traceback in error log.

### Notebook
The notebook looks like this:

![Sequence](http://i.imgur.com/wXSw99w.png)

It categorizes every data point by ```window_name``` and ```exe``` using custom ```OrderedDict``` tables.

Different plots are available:
- ```plot_day_sequence_chart``` similar to Gantt chart but with top ```N``` categories (above picture).
- ```plot_top_categories``` plots top ```N``` categories of all time.
- ```plot_top_by_date``` same as above but splits each category by days.
- ```plot_category_by_day``` plots one category usage each day.
- ```plot_timeline_by_category_time``` same as above but for top ```N``` categories.

## Installation
I recommend using [Anaconda](https://www.continuum.io/downloads)

To install necessary components for the polling script:
```
conda install pywin32 psutil ujson
```
To log windows every time computer starts, put link to the script in startup folder.

For the notebook:
```
conda install pandas seaborn
```
