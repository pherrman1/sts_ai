"""Bounded A3 TRAIN/VALIDATION training; no corpus access or TEST evaluation.

Callers supply the same TRAIN-derived feature projection to both model families.
Optional small grids and budgets exist for synthetic CPU tests only. Artifacts
contain Python predictors; this module does not implement native MLP inference.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path

import numpy as np

XGB_GRID = tuple(dict(max_depth=d, eta=e, min_child_weight=w)
                 for d, e, w in itertools.product((4, 6, 8), (.03, .06), (10, 30)))
MLP_RECIPES = tuple(dict(lr=lr, weight_decay=wd, dropout=drop)
                    for lr, wd, drop in itertools.product((1e-3, 3e-4, 1e-4), (1e-4, 1e-3), (0., .1)))


def array_hash(value):
    """Hash dtype, shape and canonical contiguous bytes, not container metadata."""
    a = np.ascontiguousarray(value)
    h = hashlib.sha256(f'{a.dtype}:{a.shape}:'.encode())
    h.update(a.tobytes())
    return h.hexdigest()


def versions():
    import torch
    import xgboost
    return dict(numpy=np.__version__, xgboost=xgboost.__version__,
                torch=torch.__version__, cuda=torch.version.cuda,
                cudnn=torch.backends.cudnn.version(),
                gpu=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])


def _nll(y, p):
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-15, 1 - 1e-15)
    return float(np.mean(-y * np.log(p) - (1 - y) * np.log1p(-p)))


def _inputs(X_train, y_train, X_val, y_val, feature_names):
    names = tuple(feature_names)
    if not names or len(names) != len(set(names)):
        raise ValueError('feature names must be nonempty and unique')
    result = []
    for X, y in ((X_train, y_train), (X_val, y_val)):
        X, y = np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.float32)
        if X.ndim != 2 or X.shape[1] != len(names) or not len(X):
            raise ValueError('nonempty matrix must match selected feature names')
        if y.shape != (len(X),) or not np.isin(y, [0, 1]).all():
            raise ValueError('labels must be exactly binary and aligned')
        if not np.isfinite(X).all():
            raise ValueError('features must be finite')
        result.extend((X, y))
    return (*result, names)


class _Projection:
    def _project(self, X, feature_names=None):
        X = np.asarray(X, dtype=np.float32)
        if X.ndim != 2:
            raise ValueError('expected a feature matrix')
        if feature_names is not None:
            names = tuple(feature_names)
            if len(names) != X.shape[1] or len(names) != len(set(names)):
                raise ValueError('input feature names must be unique and match matrix')
            lookup = {name: i for i, name in enumerate(names)}
            try:
                X = X[:, [lookup[name] for name in self.feature_names]]
            except KeyError as exc:
                raise ValueError(f'missing model feature {exc}') from exc
        if X.shape[1] != len(self.feature_names) or not np.isfinite(X).all():
            raise ValueError('invalid projected model input')
        return X


class XGBPredictor(_Projection):
    def __init__(self, booster, feature_names):
        self.booster, self.feature_names = booster, tuple(feature_names)

    def predict(self, X, feature_names=None):
        # Projection already validates feature identity/order. Avoid rebuilding
        # a DMatrix (and its default thread pool) for every resource probe.
        return self.booster.inplace_predict(self._project(X, feature_names))

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        self.booster.save_model(directory / 'model.ubj')
        (directory / 'predictor.json').write_text(json.dumps(dict(
            kind='xgb', feature_names=self.feature_names), indent=2) + '\n')


def xgb_parameters(feature_names, *, monotone=False, threads=1):
    if threads < 1:
        raise ValueError('threads must be positive')
    if monotone and 'curHp' not in feature_names:
        raise ValueError('X2 requires curHp in TRAIN-selected features')
    params = dict(objective='binary:logistic', eval_metric='logloss', tree_method='hist',
                  device='cpu', subsample=.8, colsample_bytree=.7, max_bin=256,
                  seed=0, nthread=threads)
    if monotone:
        params['monotone_constraints'] = '(' + ','.join(
            '1' if name == 'curHp' else '0' for name in feature_names) + ')'
    return params


def train_xgb_fixed(X_train, y_train, X_val, y_val, feature_names, *, params,
                    max_rounds=2500, patience=50):
    """Retrain selected full parameters (including half-TRAIN diagnostic)."""
    import xgboost as xgb
    X_train, y_train, X_val, y_val, names = _inputs(
        X_train, y_train, X_val, y_val, feature_names)
    if not 1 <= max_rounds <= 2500 or not 1 <= patience <= 50:
        raise ValueError('XGB training budget exceeds A3 limits')
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=list(names))
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=list(names))
    booster = xgb.train(dict(params), dtrain, num_boost_round=max_rounds,
                        evals=[(dval, 'validation')], early_stopping_rounds=patience,
                        verbose_eval=False)
    # Persist precisely the best tree prefix; default Booster.predict otherwise
    # also uses the extra patience rounds retained by early stopping.
    count = booster.best_iteration + 1
    booster = booster[:count]
    predictor = XGBPredictor(booster, names)
    return predictor, dict(params=dict(params), tree_count=count,
                           validation_nll=_nll(y_val, predictor.predict(X_val)),
                           resolved_booster_config=json.loads(booster.save_config()),
                           max_rounds=max_rounds, patience=patience)


def train_xgb(X_train, y_train, X_val, y_val, feature_names, *, monotone=False,
              grid=None, max_rounds=2500, patience=50, threads=1):
    grid = XGB_GRID if grid is None else tuple(grid)
    if not 1 <= len(grid) <= 12:
        raise ValueError('XGB requires 1..12 configurations')
    base = xgb_parameters(feature_names, monotone=monotone, threads=threads)
    best, selected, trials = None, None, []
    for recipe in grid:
        if set(recipe) != {'max_depth', 'eta', 'min_child_weight'}:
            raise ValueError('grid may change only depth, eta, min_child_weight')
        predictor, trial = train_xgb_fixed(X_train, y_train, X_val, y_val,
                                           feature_names, params={**base, **recipe},
                                           max_rounds=max_rounds, patience=patience)
        trials.append(trial)
        if selected is None or trial['validation_nll'] < selected['validation_nll']:
            best, selected = predictor, trial
    return best, dict(arm='X2' if monotone else 'X1', selected=selected,
                      trials=trials, versions=versions())


def train_normalization(X_train):
    X = np.asarray(X_train, dtype=np.float64)
    if X.ndim != 2 or not len(X) or not np.isfinite(X).all():
        raise ValueError('normalization requires finite nonempty TRAIN matrix')
    mean = X.mean(axis=0).astype(np.float32)
    std = X.std(axis=0).astype(np.float32)
    std[std < 1e-12] = 1.
    return mean, std


def _network(width, dropout):
    import torch.nn as nn
    return nn.Sequential(nn.Linear(width, 64), nn.GELU(), nn.Dropout(dropout),
                         nn.Linear(64, 32), nn.GELU(), nn.Linear(32, 1))


class MLPPredictor(_Projection):
    def __init__(self, model, feature_names, mean, std, dropout):
        self.model = model.cpu().eval()
        self.feature_names = tuple(feature_names)
        self.mean, self.std = np.array(mean, copy=True), np.array(std, copy=True)
        self.dropout = dropout

    def predict(self, X, feature_names=None):
        import torch
        X = self._project(X, feature_names)
        chunks = []
        with torch.no_grad():
            for start in range(0, len(X), 8192):
                normalized = (X[start:start + 8192] - self.mean) / self.std
                chunks.append(torch.sigmoid(self.model(torch.from_numpy(normalized))).numpy().ravel())
        return np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)

    def save(self, directory):
        import torch
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        torch.save(self.model.state_dict(), directory / 'model.pt')
        np.savez(directory / 'normalization.npz', mean=self.mean, std=self.std)
        (directory / 'predictor.json').write_text(json.dumps(dict(
            kind='mlp', feature_names=self.feature_names, dropout=self.dropout,
            mean_hash=array_hash(self.mean), std_hash=array_hash(self.std)), indent=2) + '\n')


def load_predictor(directory):
    directory = Path(directory)
    meta = json.loads((directory / 'predictor.json').read_text())
    if meta['kind'] == 'xgb':
        import xgboost as xgb
        booster = xgb.Booster()
        booster.load_model(directory / 'model.ubj')
        return XGBPredictor(booster, meta['feature_names'])
    if meta['kind'] != 'mlp':
        raise ValueError('unknown predictor kind')
    import torch
    with np.load(directory / 'normalization.npz', allow_pickle=False) as arrays:
        mean, std = arrays['mean'], arrays['std']
    if array_hash(mean) != meta['mean_hash'] or array_hash(std) != meta['std_hash']:
        raise ValueError('normalization hash mismatch')
    model = _network(len(meta['feature_names']), meta['dropout'])
    model.load_state_dict(torch.load(directory / 'model.pt', weights_only=True, map_location='cpu'))
    return MLPPredictor(model, meta['feature_names'], mean, std, meta['dropout'])


def _fit_mlp(X_train, y_train, X_val, y_val, names, mean, std, recipe,
             seed, max_epochs, patience, batch_size, device):
    import torch
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    model = _network(len(names), recipe['dropout']).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=recipe['lr'],
                                  weight_decay=recipe['weight_decay'])
    loss_fn = torch.nn.BCEWithLogitsLoss()
    generator = torch.Generator(device='cpu').manual_seed(seed)
    # Keep the dataset on CPU and transfer batches only, bounding GPU memory.
    train = torch.from_numpy((X_train - mean) / std)
    target = torch.from_numpy(y_train)
    val = torch.from_numpy((X_val - mean) / std)
    val_y = torch.from_numpy(y_val)
    best_loss, best_state, best_epoch = float('inf'), None, 0
    for epoch in range(1, max_epochs + 1):
        model.train()
        order = torch.randperm(len(train), generator=generator)
        for indices in order.split(batch_size):
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(train[indices].to(device)).ravel(), target[indices].to(device))
            loss.backward()
            optimizer.step()
        model.eval()
        total = 0.
        with torch.no_grad():
            for start in range(0, len(val), batch_size):
                stop = min(start + batch_size, len(val))
                loss = loss_fn(model(val[start:stop].to(device)).ravel(), val_y[start:stop].to(device))
                total += float(loss.item()) * (stop - start)
        score = total / len(val)
        if score < best_loss:
            best_loss, best_epoch = score, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if epoch - best_epoch >= patience:
            break
    if best_state is None:
        raise ValueError('MLP produced no finite validation checkpoint')
    model.load_state_dict(best_state)
    predictor = MLPPredictor(model, names, mean, std, recipe['dropout'])
    return predictor, dict(recipe=dict(recipe), seed=seed, best_epoch=best_epoch,
                           epochs_run=epoch, validation_nll=_nll(y_val, predictor.predict(X_val)))


def _configure_cuda_determinism(device):
    if str(device).split(':', 1)[0] != 'cuda':
        return
    # Set this before any CUDA availability/initialization calls. PyTorch's
    # deterministic GEMM requires one of the documented cuBLAS workspaces.
    configured = os.environ.get('CUBLAS_WORKSPACE_CONFIG')
    if configured is not None and configured not in (':4096:8', ':16:8'):
        raise ValueError('unsupported CUBLAS_WORKSPACE_CONFIG for deterministic CUDA')
    if configured is None:
        import torch
        if torch.cuda.is_initialized():
            raise ValueError('configure CUBLAS_WORKSPACE_CONFIG before CUDA initialization')
        os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'


def train_mlp(X_train, y_train, X_val, y_val, feature_names, *, recipes=None,
              seeds=(0, 1, 2), max_epochs=60, patience=8, batch_size=8192,
              threads=1, device='cpu'):
    _configure_cuda_determinism(device)
    import torch
    X_train, y_train, X_val, y_val, names = _inputs(
        X_train, y_train, X_val, y_val, feature_names)
    recipes = MLP_RECIPES if recipes is None else tuple(recipes)
    if not 1 <= len(recipes) <= 12 or not 1 <= max_epochs <= 60 or not 1 <= patience <= 8:
        raise ValueError('MLP recipe/epoch/patience budget exceeds A3 limits')
    if tuple(seeds) != (0, 1, 2):
        raise ValueError('selected MLP recipe must be retrained with seeds 0,1,2')
    if batch_size < 1 or threads < 1:
        raise ValueError('batch size and threads must be positive')
    for recipe in recipes:
        if set(recipe) != {'lr', 'weight_decay', 'dropout'} or recipe['dropout'] not in (0., .1):
            raise ValueError('invalid MLP recipe')
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    mean, std = train_normalization(X_train)
    args = (X_train, y_train, X_val, y_val, names, mean, std)
    kwargs = dict(max_epochs=max_epochs, patience=patience, batch_size=batch_size, device=device)
    trials = []
    for recipe in recipes:
        _, trial = _fit_mlp(*args, recipe=recipe, seed=0, **kwargs)
        trials.append(trial)
    recipe = min(trials, key=lambda item: item['validation_nll'])['recipe']
    retrains, best, selected = [], None, None
    for seed in seeds:
        predictor, trial = _fit_mlp(*args, recipe=recipe, seed=seed, **kwargs)
        retrains.append(trial)
        if selected is None or trial['validation_nll'] < selected['validation_nll']:
            best, selected = predictor, trial
    scores = [r['validation_nll'] for r in retrains]
    return best, dict(arm='M1', selected=selected, trials=trials, retrains=retrains,
                      validation_spread=dict(min=min(scores), max=max(scores),
                                             mean=float(np.mean(scores)), std=float(np.std(scores))),
                      normalization=dict(mean_hash=array_hash(mean), std_hash=array_hash(std)),
                      max_epochs=max_epochs, patience=patience, batch_size=batch_size,
                      threads=threads, device=device, tf32=False, versions=versions())
