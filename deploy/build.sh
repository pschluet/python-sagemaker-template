#!/bin/bash
# Pass no arguments to only run the build.
# Pass "test" as the first argument to only run the test (no build).
test_arg=$1

# Used to make the $(pwd) in the volume mount below work on Windows
export MSYS_NO_PATHCONV=1

# Set environment variables
source set_env.sh

# Run the tests
if [ $# -gt 0 ] && [ $test_arg == 'test' ]; then
    docker run -v $(pwd)/../container/local_test/test_dir:/opt/ml -v $(pwd)/../container/algorithm:/opt/program --entrypoint /opt/program/test python-sagemaker-base
else
    # Build the SageMaker docker container
    docker build -t python-sagemaker-base ../container/
fi
