#!/usr/bin/env python

import os
from .Worker import worker
from .TaskTree import TaskTree
from functools import partial

SRCTEMPLATE = "http://nasanex.s3.amazonaws.com/NEX-GDDP/BCSD/{scenario}/day/atmos/{variable}/r1i1p1/v1.0/{variable}_day_BCSD_{scenario}_r1i1p1_{model}_{year}.nc"
FILETEMPLATE = "{function}_{variable}_{scenario}_{model}_{year}.tif"

SCENARIOS = ["historical","rcp85","rcp45"]
VARIABLES = ["pr","tasmax","tasmin"]
MODELS =    ['ACCESS1-0',
             'BNU-ESM',
             'CCSM4',
             'CESM1-BGC',
             'CNRM-CM5',
             'CSIRO-Mk3-6-0',
             'CanESM2',
             'GFDL-CM3',
             'GFDL-ESM2G',
             'GFDL-ESM2M',
             'IPSL-CM5A-LR',
             'IPSL-CM5A-MR',
             'MIROC-ESM-CHEM',
             'MIROC-ESM',
             'MIROC5',
             'MPI-ESM-LR',
             'MPI-ESM-MR',
             'MRI-CGCM3',
             'NorESM1-M',
             'bcc-csm1-1',
             'inmcm4']
ENSEMBLE = 'ens'
SOURCEDATA = 'src'
STARTYEAR = 1950
PROJYEAR = 2006
ENDYEAR = 2100

_Formulae = {}

def getTemplate(f="{function}", v="{variable}", s="{scenario}", m="{model}", y="{year}"):
    return keyName(f, v, s, m, y)

def keyName(f, v, s, m, y):
    if f == SOURCEDATA:
        return srcName(v, s, m, y)
    return FILETEMPLATE.format(
        function=f, variable=v, scenario=s, model=m, year=str(y))

def srcName(v, s, m, y):
    return SRCTEMPLATE.format(
        variable=v, scenario=s, model=m, year=str(y))

def validateKey(key):
    vals = parseKey(key)
    yrs = vals[4].split('-')
    if not len(vals) == 5:
        raise Exception('Invalid key {}; Must be of format {}'.format(
            key, FILETEMPLATE))
    elif not vals[0] in _Formulae:
        raise Exception('Invalid key {}; Formula {} must be one of {}'.format(
            key, vals[0], ','.join(_Formulae.keys())))
    elif not vals[1] in VARIABLES:
        raise Exception('Invalid key {}; Variable {} must be one of {}'.format(
            key, vals[1], ','.join(VARIABLES)))
    elif not vals[2] in SCENARIOS:
        raise Exception('Invalid key {}; Scenario {} must be one of {}'.format(
            key, vals[2], ','.join(SCENARIOS)))
    elif not (vals[3] in MODELS or vals[3] == ENSEMBLE):
        raise Exception('Invalid key {}; Model {} must be one of {},{}'.format(
            key, vals[3], ','.join(MODELS), ENSEMBLE))
    elif not ((int(yrs[0]) >= STARTYEAR and int(yrs[0]) <= ENDYEAR) and
          (len(yrs) == 1 or (int(yrs[1]) >= STARTYEAR and int(yrs[1]) <= ENDYEAR))):
        raise Exception('Invalid key {}; Year(s) {} must be between {},{}'.format(
            key, yrs, STARTYEAR, ENDYEAR))
    return keyName(*vals)

def parseKey(key):
    vals = os.path.splitext(key)[0].split('_')
    return vals

def getFormula(key):
    f = parseKey(key)[0]
    return _Formulae[f]

def getParams(key):
    return parseKey(key)[1:]

def listFormulae():
    return _Formulae.keys()

def dependencyTree(keys, client, skipExisting=False, poolargs={}):
    '''yeilds depth-first unique dependencies for a given set of task keys'''
    tree = TaskTree(**poolargs)
    if type(keys) is str:
        keys = [keys]
    for key in keys:
        key = validateKey(key)
        if not tree.exists(key):
            _addDependencies(tree, key, client, skipExisting)
    tree.skip_undefined()
    return tree

def _addDependencies(tree, key, client, skipExisting=False):
    if skipExisting and client.objExists2(key):
        tree.skip_task(key)
        return
    formula = getFormula(key)
    requires = formula.requires(*getParams(key))
    tree.add(formula.getFunction(), key, requires)
    for k in requires:
        if not tree.exists(k):
            if k[:4] != 'http':
                _addDependencies(tree, k, client, skipExisting)
            else:
                tree.skip_task(k)

def registerFormula(ftype, name=None, requires=SOURCEDATA, function=None, **kwargs):
    if name is None:
        name = '{}-{}'.format(function, requires)
    if name in _Formulae:
        raise Exception("Formula {} already defined".format(name))
    _Formulae[name] = ftype(name, requires, function, **kwargs)

def buildKey(key, *args, **kwargs):
    formula = getFormula(key)
    params = getParams(key)
    requires = formula.requires(*params)
    return formula.getFunction()(key, requires, *args, **kwargs)

class Formula:
    def __init__(self, name, requires, function, description=''):
        self.name = name
        self.function = function
        self._requires = requires
        self.description = description
    def __repr__(self):
        return getTemplate(self.name)
    def requires(self, v, s, m, y):
        if int(y) < PROJYEAR:
            s = SCENARIOS[0]
        return [keyName(self._requires, v, s, m, y)]
    def yields(self, v, s, m, y):
        try:
            if int(y) < PROJYEAR:
                s = SCENARIOS[0]
        except:
            y1, y2 = y.split('-')
            if int(y1) < PROJYEAR and int(y2) < PROJYEAR:
                s = SCENARIOS[0]
        return keyName(self.name, v, s, m, y)
    def getFunction(self):
        return partial(worker, function=self.function)

class Formula2(Formula):
    def __init__(self, name, requires, function, requires2, description=''):
        self.name = name
        self.function = function
        self._requires = requires
        self._requires2 = requires2
    def requires(self, v, s, m, y):
        try:
            if int(y) < PROJYEAR:
                s = SCENARIOS[0]
        except:
            y1, y2 = y.split('-')
            if int(y1) < PROJYEAR and int(y2) < PROJYEAR:
                s = SCENARIOS[0]
        return [
            keyName(self._requires, v, s, m, y),
            self._requires2.format(variable=v, scenario=s, model=m, year=y)
        ]

class TimeFormula(Formula):
    def __repr__(self):
        return getTemplate(self.name, y="{startYear}-{endYear}")
    def requires(self, v, s, m, y):
        try:
            y1, y2 = y.split('-')
        except ValueError:
            raise Exception(f'Timeseries year must be of format "<start>-<end>", got "{y}"')
        return [
            keyName(self._requires, v, SCENARIOS[0], m, i)
            if i < PROJYEAR else
            keyName(self._requires, v, s, m, i)
            for i in range(int(y1), int(y2)+1)
        ]

class EnsembleFormula(Formula):
    def __repr__(self):
        return getTemplate(self.name, m=ENSEMBLE, y="{startYear}-{endYear}")
    def yields(self, v, s, m, y):
        return keyName(self.name, v, s, ENSEMBLE, y)
    def requires(self, v, s, _, y):
        return [keyName(self._requires, v, s, m, y) for m in MODELS]
