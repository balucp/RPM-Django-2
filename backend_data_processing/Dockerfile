# Use the official Python image as a base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED 1

# Update package index
RUN apt-get update

# Install core build dependencies
RUN apt-get install -y --no-install-recommends build-essential python3-dev

# Install math libraries
RUN apt-get install -y --no-install-recommends libopenblas-dev liblapack-dev gfortran

# Install git
RUN apt-get install -y --no-install-recommends git

# Clean up apt cache
RUN rm -rf /var/lib/apt/lists/*

# Install curl for healthchecks
RUN apt-get update && apt-get install -y curl

# Set work directory
WORKDIR /app

# Copy .env and shell script
COPY .env.dev ./
COPY replace_git_credentials.sh ./

# Make the shell script executable
RUN chmod +x replace_git_credentials.sh

# Copy the requirements file
COPY requirements.txt /app/

# Execute the shell script to replace credentials in requirements.txt
RUN ./replace_git_credentials.sh

# Install dependencies
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --no-deps -r requirements.txt

# Copy the project
COPY . /app/

# Set the work directory to the Django project directory
WORKDIR /app/dataprocessing

# Copy and set the entrypoint script
COPY ./entrypoint.sh /entrypoint.sh
COPY ./wait-for-celery.sh /wait-for-celery.sh
RUN chmod +x /entrypoint.sh /wait-for-celery.sh

ENTRYPOINT ["/entrypoint.sh"]

# Expose port 8000 for Django
EXPOSE 9000

# Run Django development server
CMD ["gunicorn", "dataprocessing.wsgi:application", "--bind", "0.0.0.0:9000", "--workers", "9"]
