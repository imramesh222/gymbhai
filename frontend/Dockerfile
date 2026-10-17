FROM node:24-slim

# frontend/ and shared/ side by side, as in the repo (PLAN.md §17): the source
# is mounted over these by docker-compose.yml.
WORKDIR /work/frontend

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Must listen on 0.0.0.0 for the published port, and phones on the LAN, to
# reach it.
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]
