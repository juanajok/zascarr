FROM mcr.microsoft.com/playwright:v1.56.1-noble
WORKDIR /work
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY playwright.config.ts ./
COPY tests ./tests
COPY fixtures ./fixtures
COPY agents ./agents
CMD ["npx", "playwright", "test"]
