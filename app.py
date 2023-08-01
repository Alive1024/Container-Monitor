"""
A simple web application based on Flask.
"""
from threading import Thread
import time

from flask import Flask, render_template

from collector import StatsCollector

# >>>>>>>>>>>>>>>>>>>>>>>>>>> Custom Configs >>>>>>>>>>>>>>>>>>>>>>>>>>>
# Collection interval, in seconds
COLLECTION_INTERVAL = 1.5

# Pause threshold for collection thread, in seconds.
# State collection will be paused if there is no client accessing latest states 
# lasting for more than this threshold.
PAUSE_THRESHOLD = 30

# AJAX request interval of client, in milliseconds
AJAX_REQUEST_INTERVAL = 1500

# Page title displayed in webpage header
PAGE_TITLE = "PRIS-727 Server Monitor"
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

app = Flask(__name__)

# [only for dev]
app.config["TEMPLATES_AUTO_RELOAD"] = True

# >>>>>>>>>>>>>>>>>>>>>>>>>>> Current Stats >>>>>>>>>>>>>>>>>>>>>>>>>>>
class CurrentStats:
    def __init__(self):
        self.prev_time = time.time()
        self.stats = None

    def set_stats(self, stats):
        self.stats = stats

    def get_stats(self):
        self.prev_time = time.time()  # update access time
        while self.stats is None:
            time.sleep(COLLECTION_INTERVAL)
        return self.stats


# The global varible representing current stats
CURRENT_STATS = CurrentStats()
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

# >>>>>>>>>>>>>>>>>>>>>>>>>>> Collection Thread >>>>>>>>>>>>>>>>>>>>>>>>>>>
class CollectionThread(Thread):
    def __init__(self):
        super().__init__()
        self.collector = StatsCollector()

    def run(self):
        while True:
            # If there is request within PAUSE_THRESHOLD, refresh `CURRENT_STATS`
            if time.time() - CURRENT_STATS.prev_time < PAUSE_THRESHOLD:
                CURRENT_STATS.set_stats(self.collector.get_stats())

            # Otherwise, pause collecting latest stats and set stats as `None`
            else:
                CURRENT_STATS.set_stats(None)

            time.sleep(COLLECTION_INTERVAL)


# Create and start the collection thread
collection_thread = CollectionThread()
collection_thread.start()
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

# >>>>>>>>>>>>>>>>>>>>>>>>>>> Flask Route Functions >>>>>>>>>>>>>>>>>>>>>>>>>>>
@app.route("/")
def index():
    return render_template("index.html", 
                           ajax_request_interval=AJAX_REQUEST_INTERVAL,
                           page_title=PAGE_TITLE)


@app.route("/query")
def query():
    """
    For AJAX requets. Return JSON.
    """
    return CURRENT_STATS.get_stats()

# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
