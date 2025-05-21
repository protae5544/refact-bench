FROM docker:27.5.1-cli

# Install Python and required dependencies
RUN apk add --no-cache python3 python3-dev py3-pip git cmake build-base apache-arrow-dev

# Force symlink to set Python3 as the default python
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Install SWE repo
RUN git clone https://github.com/princeton-nlp/SWE-bench.git /SWE-bench
WORKDIR /SWE-bench
RUN python -m venv .venv
RUN . .venv/bin/activate      && \
    pip install --upgrade pip && \
    pip install "protobuf<4"  && \
    pip install -e . 

WORKDIR /app
