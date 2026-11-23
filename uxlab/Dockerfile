FROM mcr.microsoft.com/playwright:v1.56.1-noble
WORKDIR /work
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY playwright.config.ts ./
COPY tests ./tests
COPY fixtures ./fixtures
CMD ["npx", "playwright", "test"]
