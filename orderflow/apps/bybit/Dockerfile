FROM node:18-alpine

WORKDIR /app

# Copy package.json and yarn.lock files
COPY apps/gateio/package.json ./package.json
COPY apps/gateio/yarn.lock ./yarn.lock

# Install dependencies
RUN yarn install

# Copy tsconfig files
COPY tsconfig.json ./
COPY tsconfig.build.json ./

# Copy required libraries
COPY libs/ ./libs/

# Copy everything from the apps/gateio directory to the Docker image
COPY apps/gateio/ .

# Build the application
RUN yarn build:gateio

EXPOSE 3000

CMD [ "node", "dist/main.js" ]
