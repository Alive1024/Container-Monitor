# Adapted from https://github.com/XuehaiPan/nvitop/blob/main/Dockerfile
FROM ubuntu

# Update APT sources
RUN . /etc/os-release && [ "${NAME}" = "Ubuntu" ] && \
    echo "deb [arch=amd64] http://archive.ubuntu.com/ubuntu ${UBUNTU_CODENAME} main universe" > /etc/apt/sources.list && \
    echo "deb [arch=amd64] http://archive.ubuntu.com/ubuntu ${UBUNTU_CODENAME}-updates main universe" >> /etc/apt/sources.list && \
    echo "deb [arch=amd64] http://archive.ubuntu.com/ubuntu ${UBUNTU_CODENAME}-security main universe" >> /etc/apt/sources.list

# Install Python3, nginx and supervisor
RUN apt-get update && \
    apt-get install --quiet --yes --no-install-recommends python3-dev python3-venv locales nginx supervisor && \
    rm -rf /var/lib/apt/lists/*

# Setup locale
ENV LC_ALL=C.UTF-8
RUN update-locale LC_ALL="C.UTF-8"

# Setup environment
RUN python3 -m venv /venv && \
    . /venv/bin/activate && \
    python3 -m pip install --upgrade pip setuptools && \
    rm -rf /root/.cache && \
    echo && echo && echo "source /venv/bin/activate" >> /root/.bashrc
ENV SHELL /bin/bash

# Install Python dependencies
COPY . /Monitor
WORKDIR /Monitor
RUN . /venv/bin/activate && \
    python3 -m pip install -r requirements.txt && \
    rm -rf /root/.cache

COPY configs/supervisor_gunicorn.conf /etc/supervisor/conf.d
COPY configs/supervisor_nginx.conf /etc/supervisor/conf.d

RUN echo "service supervisor start" >> /root/.bashrc
# rm /etc/nginx/sites-available/default
ENTRYPOINT [ "/bin/bash" ]
