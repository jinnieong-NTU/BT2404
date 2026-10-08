# Google Cloud Run Dockerfile
# Python 3.12 with CBC solver and FastAPI backend
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

# Install system dependencies including CBC solver and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    coinor-cbc \
    coinor-libcbc-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source, frontend assets, and faculty settings
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY faculty_settings.json /app/backend/faculty_settings.json

WORKDIR /app/backend

# Verify CBC solver is working
RUN python -c "import pulp; prob = pulp.LpProblem('test', pulp.LpMinimize); x = pulp.LpVariable('x', 0); prob += x; prob.solve(pulp.PULP_CBC_CMD(msg=False)); print('CBC Solver test status:', pulp.LpStatus[prob.status])"

EXPOSE 8080

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
