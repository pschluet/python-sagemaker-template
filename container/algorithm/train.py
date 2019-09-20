#!/usr/bin/env python

# A sample training component that trains a simple scikit-learn decision tree model.
# This implementation works in File mode and makes no assumptions about the input file names.
# Input is specified as CSV with a data point in each row and the labels in the first column.

from __future__ import print_function

import os
import json
from joblib import dump
import sys
import traceback

import numpy as np
import pandas as pd

from sklearn import tree
from sklearn.model_selection import cross_val_score, StratifiedKFold

# These are the paths to where SageMaker mounts interesting things in your container.

prefix = '/opt/ml/'

input_path = prefix + 'input/data'
output_path = os.path.join(prefix, 'output')
model_path = os.path.join(prefix, 'model')
param_path = os.path.join(prefix, 'input/config/hyperparameters.json')

# This algorithm has a single channel of input data called 'training'. Since we run in
# File mode, the input files are copied to the directory specified here.
channel_name='train'
training_path = os.path.join(input_path, channel_name)

# The function to execute the training.
def train():
    print('Starting the training.')
    try:
        # Read in any hyperparameters that the user passed with the training job
        with open(param_path, 'r') as tc:
            trainingParams = json.load(tc)

        # Take the set of files and read them all into a single pandas dataframe
        input_files = [ os.path.join(training_path, file) for file in os.listdir(training_path) ]
        if len(input_files) == 0:
            raise ValueError(('There are no files in {}.\n' +
                              'This usually indicates that the channel ({}) was incorrectly specified,\n' +
                              'the data specification in S3 was incorrectly specified or the role specified\n' +
                              'does not have permission to access the data.').format(training_path, channel_name))
        raw_data = [ pd.read_csv(file, header=None) for file in input_files ]
        train_data = pd.concat(raw_data)

        # labels are in the first column
        train_y = train_data.iloc[:,0]
        train_X = train_data.iloc[:,1:]

        # Here we only support a single hyperparameter. Note that hyperparameters are always passed in as
        # strings, so we need to do any necessary conversions.
        max_leaf_nodes = trainingParams.get('max_leaf_nodes', None)
        if max_leaf_nodes is not None:
            max_leaf_nodes = int(max_leaf_nodes)

        # Now use scikit-learn's decision tree classifier to train the model.
        clf = tree.DecisionTreeClassifier(max_leaf_nodes=max_leaf_nodes)
        clf = clf.fit(train_X, train_y)

        # Evaluate the model using cross-validation
        cross_validate(
            model=clf,
            X=train_X,
            y=train_y,
            K=5
        )

        # save the model
        dump(clf, os.path.join(model_path, 'model.joblib'))
        print('Training complete.')
    except Exception as e:
        # Write out an error file. This will be returned as the failureReason in the
        # DescribeTrainingJob result.
        trc = traceback.format_exc()
        with open(os.path.join(output_path, 'failure'), 'w') as s:
            s.write('Exception during training: ' + str(e) + '\n' + trc)
        # Printing this causes the exception to be in the training job logs, as well.
        print('Exception during training: ' + str(e) + '\n' + trc, file=sys.stderr)
        # A non-zero exit code causes the training job to be marked as Failed.
        sys.exit(255)

def cross_validate(model, X, y, K):
    """Evaluate the model using K-fold cross-validation
    
    Arguments:
        model -- sci-kit learn estimator
        X {[pandas.core.frame.DataFrame]} -- feature data
        y {[pandas.core.series.Series]} -- label data
        K {[int]} -- the number of folds to use for cross-validation
    """
    score = cross_val_score(
        estimator=model,
        X=X,
        y=y,
        cv=StratifiedKFold(K)
    )
    # Print this to CloudWatch logs so hyperparameter tuning jobs can pick up on it
    # with the following regex:	-Fold-Cross-Validated::accuracy::([0-9.]+)::
    print('::{}-Fold-Cross-Validated::accuracy::{}::'.format(K, np.mean(score)))

if __name__ == '__main__':
    train()

    # A zero exit code causes the job to be marked a Succeeded.
    sys.exit(0)
