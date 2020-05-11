# Build an image that can do training and inference in SageMaker
# This is a Python 3.6 image that uses the nginx, gunicorn, flask stack
# for serving inferences in a stable way.

FROM pschluet/python-machine-learning:1.0.0

ENV PATH="/opt/program:${PATH}"

# Set up the program in the image
COPY algorithm /opt/program
WORKDIR /opt/program

