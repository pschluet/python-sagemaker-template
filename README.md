# python-sagemaker-template
A template for deploying python machine learning algorithms to Amazon SageMaker

## Description
This repo contains two Docker image definitions. The first image (in the `container` folder) contains the python installation as well as all of the python packages. This is the image that will get uploaded to Amazon to run in SageMaker. The second image (in the `notebook`) folder is built on the base image and contains a Jupyter notebook for code development purposes. This image is not used in SageMaker. It is only for local development purposes.

## Build
To build both Docker images, run the root-level `build.sh` shell script. 

## Usage
### Environment Updates
To add new packages or remove existing ones:
1. Modify the `container/requirements.txt` file to specify which packages (and their corresponding versions) that you want installed.
1. Run the root-level `build.sh` script to re-build the Docker images.

### Implement Custom Algorithm
The training code that gets executed on SageMaker training jobs is the `train` function in the `container/algorithm/train` script. Modify this function to implement your custom algorithm.

The serving code (an API that serves model predictions) that gets executed on SageMaker is the `transformation` function in the `container/algorithm/predictor.py` file. You shouldn't need to modify this code, but you can if you want to change how the API will serve predictions.

### Local Testing
To test the train function locally

```
cd container/local_test
./train_local.sh python-base
```

To test the server locally, first start the server

```
cd container/local_test
./serve_local.sh python-base
```
then send a request to the server with a sample data payload.
```
./predict.sh payload.csv
```
You should get a response back from the server with predictions.

The `container\local_test\test_dir` folder contains all of the files that are used for local testing. This folder structure gets mounted in your Docker image in SageMaker when training jobs are run and when API endpoints are deployed. The contents of this directory change depending on how you define your training job in SageMaker. Here are some modifications you can make to your local files to simulate different training job definition parameters:

- Update `input\config\hyperparameters.json` to specify specific hyperparameter inputs for your algorithm.
- Put input data files in the `input\data\train` folder.
- Model artifict outputs get written to the `model` folder during training jobs.
- Other outputs (transformed data or anything else you want) get written to the `output` folder. If your algorithm fails, write a file called `failure` to this directory that describes why the training failed. The contents of this file will be returned in the FailureReason field of the DescribeTrainingJob result (in SageMaker). For jobs that succeed, there is no reason to write this file as it will be ignored.
