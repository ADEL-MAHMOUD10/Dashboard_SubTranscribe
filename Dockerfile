FROM python:3.12

WORKDIR /app


COPY requirements.txt .

RUN apt-get update && apt-get install -y ffmpeg
RUN pip install --no-cache-dir -r requirements.txt


COPY . .


CMD ["python","./app.py"]


EXPOSE 8000
