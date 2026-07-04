FROM node:18-alpine

WORKDIR /app

# Copy package.json and yarn.lock files
COPY apps/okx/package.json ./package.json
COPY apps/okx/yarn.lock ./yarn.lock

# Install dependencies
RUN yarn install

# Copy tsconfig files
COPY tsconfig.json ./
COPY tsconfig.build.json ./

# Copy required libraries
COPY libs/ ./libs/

# Copy everything from the apps/okx directory to the Docker image
COPY apps/okx/ .

# Build the application
RUN yarn build:okx

EXPOSE 3000

CMD [ "node", "dist/main.js" ]
