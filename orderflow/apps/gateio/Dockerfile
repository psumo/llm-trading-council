FROM node:18-alpine

WORKDIR /app

# Copy package.json and yarn.lock files
COPY apps/bybit/package.json ./package.json
COPY apps/bybit/yarn.lock ./yarn.lock

# Install dependencies
RUN yarn install

# Copy tsconfig files
COPY tsconfig.json ./
COPY tsconfig.build.json ./

# Copy required libraries
COPY libs/ ./libs/

# Copy everything from the apps/bybit directory to the Docker image
COPY apps/bybit/ .

# Build the application
RUN yarn build:bybit

EXPOSE 3000

CMD [ "node", "dist/main.js" ]
