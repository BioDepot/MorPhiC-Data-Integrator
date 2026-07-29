FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        docker.io curl && \
    rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://get.docker.com/ | sh

# Set working directory
WORKDIR /app

# Copy everything into the image
COPY . /app

# Environment variable
ENV BWB_SCHED_DIR=/data

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Flask configuration (optional if provided elsewhere)
ENV FLASK_RUN_HOST=0.0.0.0

# Expose Flask's default port
EXPOSE 5000

# Run the Flask development server
#ENTRYPOINT ["flask", "run"]
