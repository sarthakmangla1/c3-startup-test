FROM --platform=linux/amd64 python:3.12.12-slim-bookworm
RUN pip install --no-cache-dir pyyaml pytest
WORKDIR /fixer
COPY fix.py run.sh /fixer/
RUN chmod +x /fixer/run.sh /fixer/fix.py
ENTRYPOINT ["/bin/sh", "/fixer/run.sh"]
