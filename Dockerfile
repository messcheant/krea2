FROM runpod/comfyui:cuda12.8

RUN apt-get update -qq && apt-get install -y -qq aria2 git wget \
  && rm -rf /var/lib/apt/lists/*

COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
