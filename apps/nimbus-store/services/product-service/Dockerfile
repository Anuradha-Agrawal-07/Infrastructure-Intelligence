FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src ./src
ENV PORT=4001
EXPOSE 4001
CMD ["node", "src/index.js"]
