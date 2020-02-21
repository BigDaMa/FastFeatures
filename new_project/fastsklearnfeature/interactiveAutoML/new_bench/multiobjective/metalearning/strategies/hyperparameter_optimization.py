import autograd.numpy as anp
import numpy as np
from pymoo.util.misc import stack
from pymoo.model.problem import Problem
import numpy as np
import pickle
from fastsklearnfeature.candidates.CandidateFeature import CandidateFeature
from fastsklearnfeature.candidates.RawFeature import RawFeature
from fastsklearnfeature.interactiveAutoML.feature_selection.ForwardSequentialSelection import ForwardSequentialSelection
from fastsklearnfeature.transformations.OneHotTransformation import OneHotTransformation
from typing import List, Dict, Set
from fastsklearnfeature.interactiveAutoML.CreditWrapper import run_pipeline
from pymoo.algorithms.so_genetic_algorithm import GA
from pymoo.factory import get_crossover, get_mutation, get_sampling
from pymoo.optimize import minimize
from pymoo.algorithms.nsga2 import NSGA2
import matplotlib.pyplot as plt
from fastsklearnfeature.interactiveAutoML.Runner import Runner
import copy
from sklearn.linear_model import LogisticRegression
from fastsklearnfeature.candidates.CandidateFeature import CandidateFeature
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import make_scorer
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score
from fastsklearnfeature.transformations.IdentityTransformation import IdentityTransformation
from fastsklearnfeature.transformations.MinMaxScalingTransformation import MinMaxScalingTransformation
from sklearn.linear_model import LogisticRegression
import pickle
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import StratifiedKFold
import argparse
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import time

from art.metrics import RobustnessVerificationTreeModelsCliqueMethod
from art.metrics import loss_sensitivity
from art.metrics import empirical_robustness
from sklearn.pipeline import FeatureUnion


from xgboost import XGBClassifier
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, GradientBoostingClassifier

from art.classifiers import XGBoostClassifier, LightGBMClassifier, SklearnClassifier
from art.attacks import HopSkipJump


from fastsklearnfeature.interactiveAutoML.feature_selection.RunAllKBestSelection import RunAllKBestSelection
from fastsklearnfeature.interactiveAutoML.feature_selection.fcbf_package import fcbf
from fastsklearnfeature.interactiveAutoML.feature_selection.fcbf_package import variance
from fastsklearnfeature.interactiveAutoML.feature_selection.fcbf_package import model_score
from fastsklearnfeature.interactiveAutoML.feature_selection.BackwardSelection import BackwardSelection
from sklearn.model_selection import train_test_split

from fastsklearnfeature.interactiveAutoML.new_bench import my_global_utils1
from fastsklearnfeature.interactiveAutoML.new_bench.multiobjective.robust_measure import unit_test_score

from sklearn.feature_selection import SelectKBest
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.svm import LinearSVC

from sklearn.feature_selection import mutual_info_classif
from sklearn.feature_selection import f_classif
from sklearn.feature_selection import chi2
from sklearn.tree import DecisionTreeClassifier
from sklearn.compose import ColumnTransformer

from fastsklearnfeature.interactiveAutoML.new_bench.multiobjective.robust_measure import robust_score_test

from fastsklearnfeature.configuration.Config import Config

from skrebate import ReliefF
from fastsklearnfeature.interactiveAutoML.feature_selection.fcbf_package import my_fisher_score

from skrebate import ReliefF
from fastsklearnfeature.interactiveAutoML.feature_selection.fcbf_package import my_fisher_score
from functools import partial
from hyperopt import fmin, hp, tpe, Trials, space_eval, STATUS_OK

from sklearn.feature_selection import mutual_info_classif
from sklearn.feature_selection import f_classif
from sklearn.feature_selection import chi2

from sklearn.model_selection import cross_val_score
from fastsklearnfeature.interactiveAutoML.fair_measure import true_positive_rate_score
from fastsklearnfeature.interactiveAutoML.new_bench.multiobjective.robust_measure import robust_score

import diffprivlib.models as models
from sklearn import preprocessing
from fastsklearnfeature.interactiveAutoML.new_bench.multiobjective.bench_utils import get_data

from fastsklearnfeature.interactiveAutoML.feature_selection.WeightedRankingSelection import WeightedRankingSelection
from fastsklearnfeature.interactiveAutoML.feature_selection.MaskSelection import MaskSelection

def map_hyper2vals(hyper):
	new_vals = {}
	for k, v in hyper.items():
		new_vals[k] = [v]
	return new_vals


def hyperparameter_optimization(X_train, X_test, y_train, y_test, names, sensitive_ids, ranking_functions= [], clf=None, min_accuracy = 0.0, min_fairness = 0.0, min_robustness = 0.0, max_number_features = None, max_search_time=np.inf, cv_splitter = None):

	start_time = time.time()

	auc_scorer = make_scorer(roc_auc_score, greater_is_better=True, needs_threshold=True)
	fair_train = make_scorer(true_positive_rate_score, greater_is_better=True, sensitive_data=X_train[:, sensitive_ids[0]])
	fair_test = make_scorer(true_positive_rate_score, greater_is_better=True, sensitive_data=X_test[:, sensitive_ids[0]])

	def f_clf1(hps):
		mask = np.zeros(len(hps), dtype=bool)
		for k, v in hps.items():
			mask[int(k.split('_')[1])] = v


		#repair number of features if neccessary
		max_k = max(int(max_number_features * X_train.shape[1]), 1)
		if np.sum(mask) > max_k:
			id_features_used = np.nonzero(mask)[0]  # indices where features are used
			np.random.shuffle(id_features_used)  # shuffle ids
			ids_tb_deactived = id_features_used[max_k:]  # deactivate features
			for item_to_remove in ids_tb_deactived:
				mask[item_to_remove] = False

		for mask_i in range(len(mask)):
			hps['f_' + str(mask_i)] = mask[mask_i]

		model = Pipeline([
			('selection', MaskSelection(mask)),
			('clf', LogisticRegression())
		])

		return model, hps

	def f_to_min1(hps):
		model, hps = f_clf1(hps)

		print("hyperopt: " + str(hps))

		if np.sum(model.named_steps['selection'].mask) == 0:
			return {'loss': 4, 'status': STATUS_OK, 'model': model, 'cv_fair': 0.0, 'cv_acc': 0.0, 'cv_robust': 0.0, 'cv_number_features': 1.0}



		robust_scorer = make_scorer(robust_score, greater_is_better=True, X=X_train, y=y_train, model=clf, feature_selector=model.named_steps['selection'], scorer=auc_scorer)

		cv = GridSearchCV(model, param_grid={'clf__C': [1.0]}, cv=cv_splitter,
						  scoring={'AUC': auc_scorer, 'Fairness': fair_train, 'Robustness': robust_scorer},
						  refit=False)
		cv.fit(X_train, pd.DataFrame(y_train))
		cv_acc = cv.cv_results_['mean_test_AUC'][0]
		cv_fair = 1.0 - cv.cv_results_['mean_test_Fairness'][0]
		cv_robust = 1.0 - cv.cv_results_['mean_test_Robustness'][0]

		cv_number_features = float(np.sum(model.named_steps['selection']._get_support_mask())) / float(len(model.named_steps['selection']._get_support_mask()))

		loss = 0.0
		if cv_acc >= min_accuracy and \
				cv_fair >= min_fairness and \
				cv_robust >= min_robustness:
			if min_fairness > 0.0:
				loss += (min_fairness - cv_fair)
			if min_accuracy > 0.0:
				loss += (min_accuracy - cv_acc)
			if min_robustness > 0.0:
				loss += (min_robustness - cv_robust)
		else:
			if min_fairness > 0.0 and cv_fair < min_fairness:
				loss += (min_fairness - cv_fair) ** 2
			if min_accuracy > 0.0 and cv_acc < min_accuracy:
				loss += (min_accuracy - cv_acc) ** 2
			if min_robustness > 0.0 and cv_robust < min_robustness:
				loss += (min_robustness - cv_robust) ** 2


		return {'loss': loss, 'status': STATUS_OK, 'model': model, 'cv_fair': cv_fair, 'cv_acc': cv_acc, 'cv_robust': cv_robust, 'cv_number_features': cv_number_features, 'updated_parameters': hps}

	space = {}
	for f_i in range(X_train.shape[1]):
		space['f_' + str(f_i)] = hp.randint('f_' + str(f_i), 2)

	cv_fair = 0
	cv_acc = 0
	cv_robust = 0
	cv_number_features = 1.0

	number_of_evaluations = 0

	trials = Trials()
	i = 1
	success = False
	while True:
		if time.time() - start_time > max_search_time:
			break
		fmin(f_to_min1, space=space, algo=tpe.suggest, max_evals=i, trials=trials)

		#update repair in database
		try:
			current_trial = trials.trials[-1]
			if type(current_trial['result']['updated_parameters']) != type(None):
				trials._dynamic_trials[-1]['misc']['vals'] = map_hyper2vals(current_trial['result']['updated_parameters'])
		except:
			print("found an error in repair")



		number_of_evaluations += 1

		cv_fair = trials.trials[-1]['result']['cv_fair']
		cv_acc = trials.trials[-1]['result']['cv_acc']
		cv_robust = trials.trials[-1]['result']['cv_robust']
		cv_number_features = trials.trials[-1]['result']['cv_number_features']

		if cv_fair >= min_fairness and cv_acc >= min_accuracy and cv_robust >= min_robustness and cv_number_features <= max_number_features:
			model = trials.trials[-1]['result']['model']

			model.fit(X_train, pd.DataFrame(y_train))

			test_acc = 0.0
			if min_accuracy > 0.0:
				test_acc = auc_scorer(model, X_test, pd.DataFrame(y_test))
			test_fair = 0.0
			if min_fairness > 0.0:
				test_fair = 1.0 - fair_test(model, X_test, pd.DataFrame(y_test))
			test_robust = 0.0
			if min_robustness > 0.0:
				test_robust = 1.0 - robust_score_test(eps=0.1, X_test=X_test, y_test=y_test, model=model.named_steps['clf'], feature_selector=model.named_steps['selection'], scorer=auc_scorer)

			if test_fair >= min_fairness and test_acc >= min_accuracy and test_robust >= min_robustness:
				print('fair: ' + str(min(cv_fair, test_fair)) + ' acc: ' + str(min(cv_acc, test_acc)) + ' robust: ' + str(min(test_robust, cv_robust)) + ' k: ' + str(cv_number_features))
				success = True
				break

		i += 1

	if not success:
		try:
			cv_fair = trials.best_trial['result']['cv_fair']
			cv_acc = trials.best_trial['result']['cv_acc']
			cv_robust = trials.best_trial['result']['cv_robust']
			cv_number_features = trials.best_trial['result']['cv_number_features']
		except:
			pass

	runtime = time.time() - start_time
	return {'time': runtime, 'success': success, 'cv_acc': cv_acc, 'cv_robust': cv_robust, 'cv_fair': cv_fair, 'cv_number_features': cv_number_features, 'cv_number_evaluations': number_of_evaluations}






