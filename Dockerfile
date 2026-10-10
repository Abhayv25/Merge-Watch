# Container image for the AWS Lambda version of Mergewatch.
#
# Lambda's own Python base images do not include git, so this starts from the
# official Python image, installs git, and adds the AWS Lambda Runtime
# Interface Client (awslambdaric), which lets any image run on Lambda.
#
#   docker build --platform linux/arm64 -t mergewatch .
#
# arm64 matches the Lambda architecture in infra/ (Graviton is cheaper) and
# builds natively on Apple Silicon Macs.

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric

COPY src/ src/

# Lambda's filesystem is read-only except /tmp, and git wants a writable HOME.
ENV HOME=/tmp \
    PYTHONUNBUFFERED=1

# Lambda runs as an unprivileged user; nothing here needs root.
USER 1000

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["src.lambda_handler.handler"]
