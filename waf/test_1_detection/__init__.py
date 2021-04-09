# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Nico Epp and Ralf Funk
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import numpy as np
import pandas as pd
from sklearn.externals import joblib
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, Normalizer
from sklearn.svm import OneClassSVM
from typing import List, Tuple
from ..base import BASE_PATH
from .. import data_sets, feature_extraction as fe
from sklearn import metrics


_file_memory = joblib.Memory(cachedir=os.path.join(BASE_PATH, 'cache'))


def get_result_line(df: pd.DataFrame) -> Tuple:
    df_train = df[df[fe.META_GROUP] == 'train']

    y = df_train[df_train[fe.META_TRUE_LABEL] == 'normal']
    train_normal_count = y.shape[0]
    train_normal_right = y[y[fe.META_TRUE_LABEL] == y[fe.META_PRED_LABEL]].shape[0]

    y = df_train[df_train[fe.META_TRUE_LABEL] == 'anomalous']
    train_anomalous_count = y.shape[0]
    train_anomalous_right = y[y[fe.META_TRUE_LABEL] == y[fe.META_PRED_LABEL]].shape[0]

    df_test = df[df[fe.META_GROUP] == 'test']

    y = df_test[df_test[fe.META_TRUE_LABEL] == 'normal']
    test_normal_count = y.shape[0]
    test_normal_right = y[y[fe.META_TRUE_LABEL] == y[fe.META_PRED_LABEL]].shape[0]

    y = df_test[df_test[fe.META_TRUE_LABEL] == 'anomalous']
    test_anomalous_count = y.shape[0]
    test_anomalous_right = y[y[fe.META_TRUE_LABEL] == y[fe.META_PRED_LABEL]].shape[0]

    return (
        train_normal_count, train_normal_right,
        train_anomalous_count, train_anomalous_right,
        test_normal_count, test_normal_right,
        test_anomalous_count, test_anomalous_right,
    )


def result_list_to_df(result_list: List) -> pd.DataFrame:
    # prepare column headers for final output
    prefix_base_list = (
        'train_normal', 'train_anomalous', 'test_normal', 'test_anomalous',
        'normal', 'anomalous', 'train', 'test', 'all',
    )
    column_headers_1 = [
        '{}_{}'.format(base, suffix)
        for base in prefix_base_list
        for suffix in ('count', 'right', 'p')]
    column_headers_2 = [
        'TOTAL_POPULATION',
        'P', 'TP', 'FN', 'TPR', 'FNR',
        'N', 'TN', 'FP', 'TNR', 'FPR',
        'f_score','accuracy'
    ]
    column_headers = np.array(column_headers_1 + column_headers_2)

    # build data frame
    df = pd.DataFrame(
        data=result_list,
        columns=column_headers[[0, 1, 3, 4, 6, 7, 9, 10]])

    # calculate sums
    df['normal_count'] = df['train_normal_count'] + df['test_normal_count']
    df['normal_right'] = df['train_normal_right'] + df['test_normal_right']
    df['anomalous_count'] = df['train_anomalous_count'] + df['test_anomalous_count']
    df['anomalous_right'] = df['train_anomalous_right'] + df['test_anomalous_right']
    df['train_count'] = df['train_normal_count'] + df['train_anomalous_count']
    df['train_right'] = df['train_normal_right'] + df['train_anomalous_right']
    df['test_count'] = df['test_normal_count'] + df['test_anomalous_count']
    df['test_right'] = df['test_normal_right'] + df['test_anomalous_right']
    df['all_count'] = df['normal_count'] + df['anomalous_count']
    df['all_right'] = df['normal_right'] + df['anomalous_right']
    for _, r in df.iterrows():
        assert r['normal_count'] + r['anomalous_count'] == r['train_count'] + r['test_count']
        assert r['normal_right'] + r['anomalous_right'] == r['train_right'] + r['test_right']

    # calculate proportions
    for s in prefix_base_list:
        df[s + '_p'] = (df[s + '_right'] / df[s + '_count']).map(
            lambda x: 0 if np.isnan(x) else round(x, 2))

    # calculate statistics
    df['TOTAL_POPULATION'] = df['test_count']

    df['P'] = df['test_normal_count']
    df['TP'] = df['test_normal_right']
    df['FN'] = df['P'] - df['TP']
    df['TPR'] = (df['TP'] / df['P']).map(lambda x: 0 if np.isnan(x) else round(x, 2))
    df['FNR'] = 1 - df['TPR']

    df['N'] = df['test_anomalous_count']
    df['TN'] = df['test_anomalous_right']
    df['FP'] = df['N'] - df['TN']
    df['TNR'] = (df['TN'] / df['N']).map(lambda x: 0 if np.isnan(x) else round(x, 2))
    df['FPR'] = 1 - df['TNR']

    df['f_score'] = ((2 * df['TP']) / (2 * df['TP'] + df['FP'] + df['FN'])).map(
        lambda x: 0 if np.isnan(x) else round(x, 2))

    df['accuracy']=(df['TP'] + df['TN'])/ (df['TP'] +df['TN'] + df['FP'] + df['FN'])

    return df.loc[:, column_headers]


def classify(ds_url, random_state, train_size_normal, train_size_anomalous, filter_constraints,
             use_scaler, use_normalizer, clf_kwargs):
    # get samples
    df = fe.get(ds_url, random_state, train_size_normal, train_size_anomalous)
    if filter_constraints:
        df = fe.filter_by(df, filter_constraints)
    X_train, y_train_true, X_test, _ = fe.feature_numbers(df)

    # make and fit classifier
    step_list = []
    if use_scaler:
        step_list.append(StandardScaler())
    if use_normalizer:
        step_list.append(Normalizer())
    #clf_kwargs.setdefault('random_state', 0)        # for reproducibility of the results
    step_list.append(OneClassSVM(**clf_kwargs))
    clf = make_pipeline(*step_list)
    clf.fit(X_train, y_train_true)
    
    # add column with predicted labels
    df.loc[df[fe.META_GROUP] == 'train', fe.META_PRED_LABEL] = clf.predict(X_train)
    df.loc[df[fe.META_GROUP] == 'test', fe.META_PRED_LABEL] = clf.predict(X_test)
    df[fe.META_PRED_LABEL] = df[fe.META_PRED_LABEL].map(
        lambda x: 'normal' if x == 1 else 'anomalous')

    return df, X_train.shape[1]


@_file_memory.cache
def do_one_class(random_state, train_size_normal, train_size_anomalous, filter_constraints,
                 use_scaler, use_normalizer):
    df_list = []
    for ds_url in data_sets.DS_URL_LIST:
        for nu in (0.1, 0.01, 0.001, 0.0001):
            for gamma in (0.1, 0.01, 0.001, 0.0001):
                df, n_features = classify(
                    ds_url=ds_url,
                    random_state=random_state,
                    train_size_normal=train_size_normal,
                    train_size_anomalous=train_size_anomalous,
                    filter_constraints=filter_constraints,
                    use_scaler=use_scaler,
                    use_normalizer=use_normalizer,
                    clf_kwargs={'nu': nu, 'gamma': gamma})

                result_line = get_result_line(df)
                res_df = result_list_to_df([result_line, ])
                res_df.insert(0, 'ds_url', ds_url)
                res_df.insert(1, 'n_features', n_features)
                res_df.insert(2, 'nu', nu)
                res_df.insert(3, 'gamma', gamma)
                df_list.append(res_df)

    df = pd.concat(df_list)         # type: pd.DataFrame
    df_list = []
    for ds_url, sub_df in df.groupby(['ds_url', ]):
        best_row = sub_df.sort_values(['f_score', 'TPR','accuracy'], ascending=False).iloc[:1, :]
        df_list.append(best_row)

    df = pd.concat(df_list)         # type: pd.DataFrame
    return df.set_index('ds_url', verify_integrity=True)


def run():
    random_state = 3
    train_size_normal = 500
    train_size_anomalous = 0

    scenario_list = (
        {
            'label': 'Using only whole request as string',
            'filter_constraints': fe.COMMON_FILTER_CONSTRAINTS['R'],
            'scaler_normalizer': False,
        },
        {
            'label': 'Including analysis of parameter values',
            'filter_constraints': {},
            'scaler_normalizer': False,
        },
        {
            'label': 'Using only whole request as string',
            'filter_constraints': fe.COMMON_FILTER_CONSTRAINTS['R'],
            'scaler_normalizer': True,
        },
        {
            'label': 'Including analysis of parameter values',
            'filter_constraints': {},
            'scaler_normalizer': True,
        },
    )
    for scenario in scenario_list:
        df = do_one_class(
            random_state=random_state,
            train_size_normal=train_size_normal,
            train_size_anomalous=train_size_anomalous,
            filter_constraints=scenario['filter_constraints'],
            use_scaler=scenario['scaler_normalizer'],
            use_normalizer=scenario['scaler_normalizer'])
        scenario['df'] = df
        

    cols = ['n_features', 'nu', 'gamma', 'TPR', 'FPR', 'f_score','accuracy']
    for scenario in scenario_list:
        print()
        print(scenario['label'], '| scaler_normalizer', scenario['scaler_normalizer'])
        print(scenario['df'].loc[:, cols])

    print()
    print('{:40s} | {:25s} | {:45s} | {:25s} | {:45s} | {:25s}'.format(
        '', 'scaler and normalizer', 'average of all 18 groups', 'best of all 18 groups', 'average of all 18 groups', 'best of all 18 groups'))
    print('{:40s} | {:25s} | {:13s} | {:13s} | {:13s} | {:25s} | {:13s} | {:25s}'.format(
        '', '', 'TPR', 'FPR', 'f1-score', 'f1-score','accuracy','accuracy'))
    for scenario in scenario_list:
        print('{:40s} | {:25s} | {:4.2f} +/- {:4.2f} | {:4.2f} +/- {:4.2f} | {:4.2f} +/- {:4.2f} | {:25.2f} | {:25.2f}| {:25.2f}'.format(
            scenario['label'],
            str(scenario['scaler_normalizer']),
            scenario['df']['TPR'].mean(), scenario['df']['TPR'].std(),
            scenario['df']['FPR'].mean(), scenario['df']['FPR'].std(),
            scenario['df']['f_score'].mean(), scenario['df']['f_score'].std(),
            scenario['df']['f_score'].max(),scenario['df']['accuracy'].mean(),scenario['df']['accuracy'].max()))
        
            
