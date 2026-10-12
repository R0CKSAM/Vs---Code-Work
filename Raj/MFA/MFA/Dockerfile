FROM node:20-alpine

WORKDIR /app

# Copy dependency files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source files
COPY . .

# Expose ports for Vite (5173) and Cloudflare Worker (8787)
EXPOSE 5173 8787

CMD ["sh", "-c", "npx wrangler d1 execute mfa-demo-db --local --file=./db/migrations/0000_init.sql && npm run dev:worker & npm run dev -- --host 0.0.0.0"]
