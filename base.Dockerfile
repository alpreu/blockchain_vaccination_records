# Pull base image.

FROM python:3.6

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY ./requirements.txt .

RUN pip install --trusted-host pypi.python.org -r requirements.txt

RUN apt-get update && apt-get install graphviz ttf-freefont less -y && apt-get clean
