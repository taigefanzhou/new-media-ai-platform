ARG NODE_BASE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm-slim
FROM ${NODE_BASE_IMAGE}

WORKDIR /app

ARG APT_MIRROR=https://repo.huaweicloud.com/debian
ARG APT_SECURITY_MIRROR=https://repo.huaweicloud.com/debian-security

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${APT_MIRROR}|g" /etc/apt/sources.list; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg chromium fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV REMOTION_DISABLE_HEADLESS_WARNING=1

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src

EXPOSE 3100
CMD ["npm", "start"]
