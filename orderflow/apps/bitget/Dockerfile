FROM node:18-alpine

WORKDIR /app

# Copy package.json and yarn.lock files
COPY apps/bitget/package.json ./package.json
COPY apps/bitget/yarn.lock ./yarn.lock

# Install dependencies
RUN yarn install

# Copy tsconfig files
COPY tsconfig.json ./
COPY tsconfig.build.json ./

# Copy required libraries
COPY libs/ ./libs/

# Copy everything from the apps/bitget directory to the Docker image
COPY apps/bitget/ .

# Build the application
RUN yarn build:bitget

EXPOSE 3000

CMD [ "node", "dist/main.js" ]
