# Disposable test fixture only; not included in the PWA runtime image.
FROM python:3.12-alpine
RUN pip install --no-cache-dir Werkzeug==3.0.6
COPY gateway-fixture.py /gateway-fixture.py
CMD ["python", "/gateway-fixture.py"]
