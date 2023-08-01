import multiprocessing

bind = "0.0.0.0:726"
backlog = 512
timeout = 30
worker_class = "gevent"
worker_connections = 100
workers = multiprocessing.cpu_count() + 1
threads = 1
daemon = True
accesslog = "/dev/null"
errorlog = "/dev/null"
loglevel = "error"
